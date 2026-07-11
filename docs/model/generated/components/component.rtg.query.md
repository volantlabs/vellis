# component.rtg.query

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgQueryEngine`
- Lifecycle: `accepted`
- Purpose: Evaluate declarative RTG queries against one coherent graph read view without mutation.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `execute` | `ExecuteRtgQuery` | in `graph: RtgGraphReadView`; in `querySpec: RtgQuerySpec`; in `queryOptions: RtgQueryOptions[0..1]`; out `result: RtgQueryResult` | `RtgQuerySpecInvalid`, `RtgQueryUnsupported` | Validate and evaluate the declarative specification over one coherent graph read view, then shape deterministic bindings, returns, and diagnostics without mutation. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| — | — | — | No package-level construction action. |

## Required capabilities

| Feature | Kind | Required contract | Cardinality |
|---|---|---|---|
| `requiredGraphReadView` | `part` | `RtgGraphReadView` | `1..1` |

## Owned state

| State feature | Type | Authority | Lifetime | Persistence |
|---|---|---|---|---|
| — | — | — | — | This component owns no abstract state. |

## Action and state effects

| Action | State / capability | Access | Contract-significant effect |
|---|---|---|---|
| `execute` | — | `none` | read only; the supplied graph view is unchanged |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.rtg.query.valid_spec` | Names are unique, references resolve, predicate operands fit their operators, and order_by refers only to returned properties. |
| `contract.rtg.query.defaults` | Data requirements default required=true; predicate case sensitivity defaults false; diagnostic inclusion defaults true with suggest-discovery guidance; absent query options mean all live states, empty overlay, and no order_by; absent order direction means ascending. |
| `contract.rtg.query.coherent_read_view` | All graph reads in one execution observe one coherent logical graph view supplied by the composition. |
| `contract.rtg.query.matching` | Anchor buckets select matching anchor types; link requirements match directed typed links between bound buckets; data requirements match directly associated typed data objects. Predicates on one data requirement must hold on the same object. |
| `contract.rtg.query.binding_expansion` | Independent required matches expand to their Cartesian product. A missing required match removes the candidate row; a missing optional match preserves it without that binding. |
| `contract.rtg.query.predicates` | exists treats missing paths as false. Equality/not-equality and contains/in membership use JSON-kind-aware equality. Relational operators match only two numbers or two strings. Substring defaults case-insensitive. Regex searches strings with only case_insensitive and multiline flags in a deterministic RE2-style subset and rejects backreferences, lookaround, and other unsupported constructs. Unresolved paths are non-matches, not errors. |
| `contract.rtg.query.lifecycle_filtering` | The default includes live and non-live objects. Explicit filtering may consult a caller overlay, which changes selection only and never canonical graph state. |
| `contract.rtg.query.deterministic_result` | Base order compares anchor UUIDs in bucket declaration order, then link UUIDs in requirement order, then data UUIDs in requirement order; absent optional data sorts before present UUIDs. order_by applies returned-property keys in caller order and keeps base order as stable tie-breaker; missing/Boolean/object/array keys sort last. rowIndex is zero-based final order. |
| `contract.rtg.query.return_shaping` | Return selection never changes matching. Bindings contain names to matched UUIDs; independent matches form a Cartesian product. Returns align one-for-one by rowIndex, include only selected records, and reconstruct selected property paths as nested JSON without delimiter ambiguity. Missing optional bindings or paths are omitted and may produce non-fatal diagnostics. |
| `contract.rtg.query.diagnostics` | Valid queries may return warning/info diagnostics without changing results. Malformed structure, unsupported operators, flags, or ordering references raise declared errors. Stable diagnostic codes distinguish unbound return requirements and unresolved returned property paths and carry generic repair guidance only. |
| `invariant.rtg.query.no_mutation` | Query has no owned state and never mutates the supplied graph read view. |
| `invariant.rtg.query.diagnostics_non_mutating` | Diagnostics explain validation or resolution outcomes without changing query matching or graph state. |
| `invariant.rtg.query.deterministic_results` | Identical coherent graph views, specifications, and options produce identical ordered bindings, returns, and diagnostics. |
| `invariant.rtg.query.deterministic_string_matching` | Substring and regex behavior uses the declared case and dialect rules rather than implementation-language-specific extensions. |
| `invariant.rtg.query.public_graph_reads_only` | Query consumes only the public coherent graph read-view capability. |
| `invariant.rtg.query.operates_over_read_view` | Live, projected, or alternative providers are substitutable when they satisfy RtgGraphReadView coherently. |
| `invariant.rtg.query.no_hidden_lifecycle_filter` | Lifecycle filtering occurs only through explicit options and never through hidden live-only defaults. |
| `invariant.rtg.query.overlay_filters_only` | A live-status overlay affects selection only and never mutates or rewrites returned graph records. |
| `invariant.rtg.query.default_includes_non_live` | Absent options include live and non-live objects. |
| `invariant.rtg.query.discovery_independent` | Query returns its own generic diagnostics and never invokes discovery or embeds application-specific schema answers. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgQueryAnchorBucket` | `attribute` | `name: String`, `anchorTypeKeys[1..*]: String` | Defined by its typed fields and action requirements. |
| `RtgQueryLinkRequirement` | `attribute` | `name: String`, `sourceBucket: String`, `targetBucket: String`, `linkTypeKeys[1..*]: String` | Defined by its typed fields and action requirements. |
| `RtgQueryPropertyPredicate` | `attribute` | `path[1..*]: String`, `operator: RtgQueryOperator`, `value[0..1]: JsonValue`, `values[0..*]: JsonScalar`, `caseSensitive: Boolean` = `false`, `regexFlags[0..*]: String` | Defined by its typed fields and action requirements. |
| `RtgQueryDataRequirement` | `attribute` | `name: String`, `anchorBucket: String`, `dataTypeKey: String`, `required: Boolean` = `true`, `predicates[0..*]: RtgQueryPropertyPredicate` | Defined by its typed fields and action requirements. |
| `RtgQueryReturnProperty` | `attribute` | `dataRequirement: String`, `path[1..*]: String` | Defined by its typed fields and action requirements. |
| `RtgQueryReturnSpec` | `attribute` | `anchorBuckets[0..*]: String`, `linkRequirements[0..*]: String`, `dataRequirements[0..*]: String`, `properties[0..*]: RtgQueryReturnProperty` | Defined by its typed fields and action requirements. |
| `RtgQueryDiagnosticOptions` | `attribute` | `includeNonFatal: Boolean` = `true`, `unknownTermGuidance: RtgQueryUnknownTermGuidance` = `RtgQueryUnknownTermGuidance::suggestDiscovery` | Defined by its typed fields and action requirements. |
| `RtgQuerySpec` | `attribute` | `anchorBuckets[1..*]: RtgQueryAnchorBucket`, `linkRequirements[0..*]: RtgQueryLinkRequirement`, `dataRequirements[0..*]: RtgQueryDataRequirement`, `returnSpec[0..1]: RtgQueryReturnSpec`, `diagnosticOptions[0..1]: RtgQueryDiagnosticOptions` | Defined by its typed fields and action requirements. |
| `RtgQueryOrderBy` | `attribute` | `dataRequirement: String`, `path[1..*]: String`, `direction: RtgQueryOrderDirection` = `RtgQueryOrderDirection::ascending` | Defined by its typed fields and action requirements. |
| `RtgQueryOptions` | `attribute` | `liveFilter: RtgQueryLiveFilter` = `RtgQueryLiveFilter::all`, `liveStatusOverlay[0..1]: JsonObject`, `orderBy[0..*]: RtgQueryOrderBy` | Defined by its typed fields and action requirements. |
| `RtgQueryBindingRow` | `attribute` | `rowIndex: Integer`, `anchors: JsonObject`, `links: JsonObject`, `dataObjects: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgQueryReturnRow` | `attribute` | `rowIndex: Integer`, `anchors: JsonObject`, `links: JsonObject`, `dataObjects: JsonObject`, `properties: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgQueryDiagnostic` | `attribute` | `severity: RtgQueryDiagnosticSeverity`, `code: String`, `message: String`, `suggestion[0..1]: String`, `affectedTerms[0..*]: String`, `diagnostic[0..1]: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgQueryResult` | `attribute` | `bindings[0..*]: RtgQueryBindingRow`, `returns[0..*]: RtgQueryReturnRow`, `diagnostics[0..*]: RtgQueryDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgQuerySpecInvalid` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgQueryUnsupported` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Model and external values |
|---|---|
| `RtgQueryOperator` | `exists`, `equals`, `notEquals` → `not_equals`, `lessThan` → `lt`, `lessThanOrEqual` → `lte`, `greaterThan` → `gt`, `greaterThanOrEqual` → `gte`, `contains`, `inSet` → `in`, `substring`, `regex` |
| `RtgQueryLiveFilter` | `all`, `live`, `nonLive` → `non_live` |
| `RtgQueryOrderDirection` | `ascending`, `descending` |
| `RtgQueryUnknownTermGuidance` | `none`, `suggestDiscovery` → `suggest_discovery` |
| `RtgQueryDiagnosticSeverity` | `warning`, `info` |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `RtgQueryBoundaryVerification` | `validQuerySpec`, `defaultSemantics`, `coherentReadView`, `matchingSemantics`, `bindingExpansion`, `predicateSemantics`, `lifecycleFiltering`, `deterministicResult`, `returnShaping`, `diagnosticSemantics`, `queryNoMutation`, `diagnosticsAreNonMutating`, `deterministicResults`, `deterministicStringMatching`, `publicGraphReadsOnly`, `operatesOverReadView`, `noHiddenLifecycleFilter`, `overlayFiltersOnly`, `defaultIncludesNonLive`, `discoveryIndependent` | `components/rtg/query/tests/test_rtg_query_contract.py` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
