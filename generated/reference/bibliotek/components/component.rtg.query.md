# component.rtg.query

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

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
| `execute` | — | `declared` | read only; the supplied graph view is unchanged. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.query.valid_spec` | `ExecuteRtgQuery` | `query.execute` | Anchor-bucket, link-requirement, and data-requirement names share one globally unique binding namespace so aggregation and constraint references are unambiguous. Every return selection, returned property, group-by, aggregation, and ordering reference resolves to its declared query element. Predicate paths and operators are structurally well formed, while a resolved runtime value of an incompatible JSON kind is a non-match under predicateSemantics rather than an invalid query. order_by refers only to returned properties, aggregation names cannot use the reserved result fields row_index or group_by, a present limit is a positive Integer, offset is a nonnegative Integer, and distinct_rows cannot be combined with aggregation. |
| `contract.rtg.query.defaults` | `ExecuteRtgQuery` | `query.execute` | Link and data requirements default required=true; predicate case sensitivity defaults false; diagnostic inclusion defaults true with suggest-discovery guidance; absent query options mean all live states, empty overlay, no order_by, no limit, offset zero, and no distinct-row projection; absent order direction means ascending. |
| `contract.rtg.query.coherent_read_view` | `ExecuteRtgQuery` | `query.execute` | The supplied graph capability presents one coherent logical view for the invocation. |
| `contract.rtg.query.matching` | `ExecuteRtgQuery` | `query.execute` | Anchor buckets select matching anchor types; required link requirements match directed typed links between bound buckets, while an optional link preserves exactly one unbound row for a source context only when no target in that bucket matches. A later optional link also preserves that row when its source bucket was left unbound by an earlier optional link. Data requirements match directly associated typed data objects. Predicates on one data requirement must hold on the same object. |
| `contract.rtg.query.binding_expansion` | `ExecuteRtgQuery` | `query.execute` | Independent required matches expand to their Cartesian product. A missing required match removes the candidate row. Optional-link expansion is left-outer by source context: matching targets produce only their bound rows, while no match across the complete target bucket produces one row without the link or target binding. |
| `contract.rtg.query.predicates` | `ExecuteRtgQuery` | `query.execute` | exists treats missing paths as false. Equality/not-equality invoke RtgQueryJsonEqual; contains/in membership invoke RtgQueryJsonContains. Relational operators match only two numbers or two strings. Substring defaults case-insensitive. Regex performs an unanchored search using the RE2 2025-11-05 syntax in UTF-8 mode; only case_insensitive and multiline may be supplied as flags. Invalid RE2 syntax and unsupported constructs such as backreferences and lookaround are rejected. Unresolved paths are non-matches, not errors. |
| `contract.rtg.query.lifecycle_filtering` | `ExecuteRtgQuery` | `query.execute` | The default includes live and non-live objects. Explicit filtering may consult a caller overlay, which changes selection only and never canonical graph state. |
| `contract.rtg.query.deterministic_result` | `ExecuteRtgQuery` | `query.execute` | Base order compares anchor UUIDs in bucket declaration order, then link UUIDs in requirement order, then data UUIDs in requirement order; absent optional bindings sort before present UUIDs. order_by applies returned-property keys in caller order, compares numbers without loss of JSON numeric precision, and keeps base order as stable tie-breaker; missing/Boolean/object/array keys sort last. Exact returned rows may be de-duplicated after projection, count aggregation counts distinct binding UUIDs by returned group properties using JSON-kind-aware canonical equality that preserves arbitrary-precision integers, and limit/offset slice the final deterministic rows. rowIndex is zero-based final order. |
| `contract.rtg.query.return_shaping` | `ExecuteRtgQuery` | `query.execute` | Return selection never changes matching. Bindings contain names to matched UUIDs; independent matches form a Cartesian product. Non-aggregate results use bindings and returns, aligned one-for-one by final rowIndex, include only selected records, and reconstruct selected property paths as nested JSON without delimiter ambiguity; their aggregations collection is empty. Aggregate results use aggregations exclusively and return empty bindings and returns. count aggregation counts distinct selected binding UUIDs globally or per group; a missing group path is represented by JSON null. Result metadata reports total rows before pagination, returned rows, and a next offset only when more rows remain. Missing bindings for declared optional requirements or missing paths in non-aggregate returns are omitted and may produce non-fatal diagnostics. Undeclared return references are invalid query specifications. |
| `contract.rtg.query.diagnostics` | `ExecuteRtgQuery` | `query.execute` | Valid queries may return warning/info diagnostics without changing results. Malformed structure, unsupported operators, flags, or unresolved references raise declared errors. The stable code query.return_property_requirement_unbound identifies a declared return requirement with no row binding; query.return_property_path_unresolved identifies a selected path that does not resolve on a bound data object. Diagnostics carry generic repair guidance only. |
| `contract.rtg.query.intentional_boundary` | `RtgQueryEngine` | `query` | Query is a read-only declarative evaluator. It owns no graph, schema, constraint, authorization, visibility, publication, persistence, transport, or UI state; validates no proposed change; infers no facts; and exposes only the modeled RTG query language rather than a general graph-database language. |
| `invariant.rtg.query.no_mutation` | `RtgQueryEngine` | `query` | Query has no owned state and never mutates the supplied graph read view. |
| `invariant.rtg.query.diagnostics_non_mutating` | `RtgQueryEngine` | `query` | Diagnostics explain validation or resolution outcomes without changing query matching or graph state. |
| `invariant.rtg.query.deterministic_results` | `RtgQueryEngine` | `query` | Identical coherent graph views, specifications, and options produce identical ordered bindings, returns, and diagnostics. |
| `invariant.rtg.query.deterministic_string_matching` | `RtgQueryEngine` | `query` | Substring and regex behavior uses the declared case and dialect rules rather than implementation-language-specific extensions. |
| `invariant.rtg.query.public_graph_reads_only` | `RtgQueryEngine` | `query` | Query consumes only the public coherent graph read-view capability. |
| `invariant.rtg.query.operates_over_read_view` | `RtgQueryEngine` | `query` | Live, projected, or alternative providers are substitutable when they satisfy RtgGraphReadView coherently. |
| `invariant.rtg.query.no_hidden_lifecycle_filter` | `RtgQueryEngine` | `query` | Lifecycle filtering occurs only through explicit options and never through hidden live-only defaults. |
| `invariant.rtg.query.overlay_filters_only` | `RtgQueryEngine` | `query` | A live-status overlay affects selection only and never mutates or rewrites returned graph records. |
| `invariant.rtg.query.default_includes_non_live` | `RtgQueryEngine` | `query` | Absent options include live and non-live objects. |
| `invariant.rtg.query.discovery_independent` | `RtgQueryEngine` | `query` | Query returns its own generic diagnostics and never invokes discovery or embeds application-specific schema answers. |
| `contract.rtg.query.execute_rtg_query.failures` | `ExecuteRtgQuery` | `query.execute` | Rejected queries leave graph state unchanged and return a structured diagnostic. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgQueryAnchorBucket` | `attribute` | `name: String`, `anchorTypeKeys[1..*]: String` | Defined by its typed fields and action requirements. |
| `RtgQueryLinkRequirement` | `attribute` | `name: String`, `sourceBucket: String`, `targetBucket: String`, `linkTypeKeys[1..*]: String`, `required: Boolean` = `true` | Defined by its typed fields and action requirements. |
| `RtgQueryPropertyPredicate` | `attribute` | `path[1..*]: String`, `operator: RtgQueryOperator`, `value[0..1]: JsonValue`, `values[0..*]: JsonScalar`, `caseSensitive: Boolean` = `false`, `regexFlags[0..*]: String` | Defined by its typed fields and action requirements. |
| `RtgQueryDataRequirement` | `attribute` | `name: String`, `anchorBucket: String`, `dataTypeKey: String`, `required: Boolean` = `true`, `predicates[0..*]: RtgQueryPropertyPredicate` | Defined by its typed fields and action requirements. |
| `RtgQueryReturnProperty` | `attribute` | `dataRequirement: String`, `path[1..*]: String` | Defined by its typed fields and action requirements. |
| `RtgQueryAggregation` | `attribute` | `name: String`, `function: RtgQueryAggregationFunction`, `binding: String` | Defined by its typed fields and action requirements. |
| `RtgQueryReturnSpec` | `attribute` | `anchorBuckets[0..*]: String`, `linkRequirements[0..*]: String`, `dataRequirements[0..*]: String`, `properties[0..*]: RtgQueryReturnProperty`, `groupBy[0..*]: RtgQueryReturnProperty`, `aggregations[0..*]: RtgQueryAggregation` | Defined by its typed fields and action requirements. |
| `RtgQueryDiagnosticOptions` | `attribute` | `includeNonFatal: Boolean` = `true`, `unknownTermGuidance: RtgQueryUnknownTermGuidance` = `RtgQueryUnknownTermGuidance::suggest_discovery` | Defined by its typed fields and action requirements. |
| `RtgQuerySpec` | `attribute` | `anchorBuckets[1..*]: RtgQueryAnchorBucket`, `linkRequirements[0..*]: RtgQueryLinkRequirement`, `dataRequirements[0..*]: RtgQueryDataRequirement`, `returnSpec[0..1]: RtgQueryReturnSpec`, `diagnosticOptions[0..1]: RtgQueryDiagnosticOptions` | Defined by its typed fields and action requirements. |
| `RtgQueryOrderBy` | `attribute` | `dataRequirement: String`, `path[1..*]: String`, `direction: RtgQueryOrderDirection` = `RtgQueryOrderDirection::ascending` | Defined by its typed fields and action requirements. |
| `RtgQueryOptions` | `attribute` | `liveFilter: RtgQueryLiveFilter` = `RtgQueryLiveFilter::'all'`, `liveStatusOverlay[0..*]: RtgQueryLiveStatusOverride`, `orderBy[0..*]: RtgQueryOrderBy`, `limit[0..1]: Integer`, `offset: Integer` = `0`, `distinctRows: Boolean` = `false` | Defined by its typed fields and action requirements. |
| `RtgQueryLiveStatusOverride` | `attribute` | `objectUuid: Uuid`, `live: Boolean` | One entry in a unique object-UUID-to-effective-live-status map used only for selection. |
| `RtgQueryNamedObjectBinding` | `attribute` | `name: String`, `objectUuid: Uuid` | One unique query name to matched graph-object identity binding. |
| `RtgQueryBindingRow` | `attribute` | `rowIndex: Integer`, `anchors[1..*]: RtgQueryNamedObjectBinding`, `links[0..*]: RtgQueryNamedObjectBinding`, `dataObjects[0..*]: RtgQueryNamedObjectBinding` | Defined by its typed fields and action requirements. |
| `RtgQueryReturnRow` | `attribute` | `rowIndex: Integer`, `anchors[0..*]: RtgQueryNamedObjectBinding`, `links[0..*]: RtgQueryNamedObjectBinding`, `dataObjects[0..*]: RtgQueryNamedObjectBinding`, `properties: JsonObject` | Binding entry collections have unique names and realization codecs encode them as JSON objects from name to UUID. |
| `RtgQueryDiagnostic` | `attribute` | `severity: RtgQueryDiagnosticSeverity`, `code: String`, `message: String`, `suggestion[0..1]: String`, `affectedTerms[0..*]: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgQueryResult` | `attribute` | `bindings[0..*]: RtgQueryBindingRow`, `returns[0..*]: RtgQueryReturnRow`, `diagnostics[0..*]: RtgQueryDiagnostic`, `aggregations[0..*]: JsonObject`, `totalRowCount: Integer`, `returnedRowCount: Integer`, `nextOffset[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RtgQuerySpecInvalid` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgQueryUnsupported` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgQueryOperator` | `exists`, `equals`, `not_equals`, `lt`, `lte`, `gt`, `gte`, `contains`, `in`, `substring`, `regex` |
| `RtgQueryLiveFilter` | `all`, `live`, `non_live` |
| `RtgQueryOrderDirection` | `ascending`, `descending` |
| `RtgQueryUnknownTermGuidance` | `none`, `suggest_discovery` |
| `RtgQueryDiagnosticSeverity` | `warning`, `info` |
| `RtgQueryAggregationFunction` | `count` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `ExecuteRtgQueryContractVerification` | `ExecuteRtgQuery` | `validQuerySpec`, `defaultSemantics`, `coherentReadView`, `matchingSemantics`, `bindingExpansion`, `predicateSemantics`, `lifecycleFiltering`, `deterministicResult`, `returnShaping`, `diagnosticSemantics`, `executeRtgQueryFailureSemantics` | `components/rtg/query/tests/test_rtg_query_contract.py#ExecuteRtgQueryContractVerification` |
| `RtgQueryBoundaryVerification` | `RtgQueryEngine` | `queryNoMutation`, `diagnosticsAreNonMutating`, `deterministicResults`, `deterministicStringMatching`, `publicGraphReadsOnly`, `operatesOverReadView`, `noHiddenLifecycleFilter`, `overlayFiltersOnly`, `defaultIncludesNonLive`, `discoveryIndependent`, `intentionalBoundary` | `components/rtg/query/tests/test_rtg_query_contract.py#RtgQueryBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
