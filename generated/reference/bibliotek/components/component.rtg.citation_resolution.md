# component.rtg.citation_resolution

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgCitationResolver`
- Lifecycle: `draft`
- Purpose: Resolve bounded graph-local citations while owning no citation, projection, graph, bridge, snapshot, or persistence state.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `resolve` | `ResolveCitation` | in `request: RtgCitationResolutionRequest`; out `result: RtgCitationResolutionRecord` | `RtgCitationResolutionInvalid` | Validate graph-qualified identity, consult the retained catalog, skip the reader when unsupported, otherwise read exactly the declared projection and return only exact anchor UUID matches without mutation. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenRtgCitationResolver` | in `catalog: RtgCitationProjectionCatalog`; in `reader: RtgCitationProjectionReader`; out `resolver: RtgCitationResolver` | None | Bind exactly one projection catalog and one read-only projection reader without opening graph storage or executing a projection. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| `catalog` | `part` | `RtgCitationProjectionCatalog` | `[1]` |
| `reader` | `part` | `RtgCitationProjectionReader` | `[1]` |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| — | — | — | This component owns no abstract state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `resolve` | `catalog` | `dependency` | Consult exactly the retained catalog for request.graphId before any projection read. |
| `resolve` | `reader` | `dependency` | Invoke the retained reader only when the catalog returned one declared projection. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.citation_resolution.catalog_capability` | `GetCitationProjection` | `catalog.getProjection` | A catalog lookup returns absence or exactly one projection declared for the requested graph and has no graph, projection, or external-storage state effect. |
| `contract.rtg.citation_resolution.reader_capability` | `ReadCitationProjection` | `reader.readProjection` | A reader executes only the supplied opaque projection, returns that projection identity unchanged with JSON-safe rows and provenance, and performs no write. |
| `contract.rtg.citation_resolution.result_semantics` | `ResolveCitation` | `resolver.resolve` | Unsupported means no catalog declaration and no reader call. Not_found preserves projection identity and provenance with no records. Resolved preserves them and returns every matching row in reader order. |
| `contract.rtg.citation_resolution.dependency_integrity` | `ResolveCitation` | `resolver.resolve` | The declared projection graphId equals the request graphId; reader output preserves graphId, queryName, and anchorBucket exactly; every row and provenance value is finite JSON; and malformed dependency output is rejected as RtgCitationResolutionInvalid. |
| `invariant.rtg.citation_resolution.graph_qualified_identity` | `RtgCitationResolver` | `resolver` | Every resolution requires a non-empty graph identifier and canonical valid graph-local UUID; labels, domain keys, and UUID-only requests are not accepted. |
| `invariant.rtg.citation_resolution.bounded_projection` | `RtgCitationResolver` | `resolver` | Resolution accepts no caller-authored query and reads only the single projection returned by the retained catalog for the named graph. |
| `invariant.rtg.citation_resolution.exact_anchor_match` | `RtgCitationResolver` | `resolver` | Every returned record exposes anchors[anchorBucket] as a valid UUID equal to the requested localUuid; nonmatching rows are never returned. |
| `invariant.rtg.citation_resolution.read_only` | `RtgCitationResolver` | `resolver` | Resolution mutates no request, projection, row, provenance, graph, descriptor, snapshot, bridge, dependency, or external storage. |
| `invariant.rtg.citation_resolution.provenance_preserved` | `RtgCitationResolver` | `resolver` | Resolved and not_found outcomes preserve an independent copy of reader-supplied provenance; unsupported outcomes contain empty provenance and no projection identity. |
| `contract.rtg.citation_resolution.intentional_boundary` | `RtgCitationResolver` | `resolver` | The component owns no state, infers no graph, chooses no arbitrary query, opens no storage, executes no MCP call, traverses no bridge, merges no identity, joins no graphs, and performs no write. |
| `contract.rtg.citation_resolution.get_projection.failures` | `GetCitationProjection` | `catalog.getProjection` | Lookup has no state effect and returns no partial projection record. |
| `contract.rtg.citation_resolution.read_projection.failures` | `ReadCitationProjection` | `reader.readProjection` | A failed read has no write effect and returns no partial bounded projection record. |
| `contract.rtg.citation_resolution.resolve.failures` | `ResolveCitation` | `resolver.resolve` | Malformed identity or dependency output returns no partial resolution and leaves requests, dependencies, and external systems unchanged. |
| `contract.rtg.citation_resolution.open.failures` | `OpenRtgCitationResolver` | `openSubject` | Construction performs no catalog lookup, projection read, graph access, network call, or external side effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgCitationResolutionRequest` | `attribute` | `graphId: String`, `localUuid: Uuid` | Canonical graph-qualified citation identity; the UUID has no meaning without graphId. |
| `RtgCitationProjectionSpec` | `attribute` | `graphId: String`, `queryName: String`, `anchorBucket: String` | Names the one approved opaque read and returned anchor bucket for a graph. |
| `RtgCitationProjectionRead` | `attribute` | `projection: RtgCitationProjectionSpec`, `rows[0..*] ordered: JsonObject`, `provenance: JsonObject` | Bounded projection rows and reader-supplied source provenance. |
| `RtgCitationResolutionRecord` | `attribute` | `status: RtgCitationResolutionStatus`, `graphId: String`, `localUuid: Uuid`, `queryName[0..1]: String`, `anchorBucket[0..1]: String`, `records[0..*] ordered: JsonObject`, `provenance: JsonObject` | Resolution outcome whose records are non-empty only when resolved and whose projection identity and provenance are present for resolved and not_found outcomes. |
| `RtgCitationResolutionInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgCitationResolutionStatus` | `resolved`, `not_found`, `unsupported` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `GetCitationProjectionContractVerification` | `GetCitationProjection` | `catalogCapability`, `getCitationProjectionFailureSemantics` | `components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#GetCitationProjectionContractVerification` |
| `ReadCitationProjectionContractVerification` | `ReadCitationProjection` | `readerCapability`, `readCitationProjectionFailureSemantics` | `components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#ReadCitationProjectionContractVerification` |
| `ResolveCitationContractVerification` | `ResolveCitation` | `resultSemantics`, `dependencyIntegrity`, `resolveCitationFailureSemantics` | `components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#ResolveCitationContractVerification` |
| `OpenRtgCitationResolverContractVerification` | `OpenRtgCitationResolver` | `openRtgCitationResolverFailureSemantics` | `components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#OpenRtgCitationResolverContractVerification` |
| `RtgCitationResolverBoundaryVerification` | `RtgCitationResolver` | `graphQualifiedIdentity`, `boundedProjection`, `exactAnchorMatch`, `readOnly`, `provenancePreserved`, `intentionalBoundary` | `components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#RtgCitationResolverBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
