---
id: component.rtg.query
type: Component
status: accepted
owner: humans
model: model/bibliotek/components/component.rtg.query.sysml
code:
  roots:
    - components/rtg/query
---

# RTG Query

## Purpose

Evaluate declarative RTG graph pattern queries over anchors, links, and associated data objects.

The component gives callers a reusable query surface for matching named anchor buckets, typed links between those buckets, data requirements over associated data objects, and simple return shaping.

## Responsibilities

- Accept query specifications with named anchor buckets and target anchor types.
- Match typed link requirements between named anchor buckets.
- Match data requirements over properties of data objects associated with matched anchors.
- Support existence, equality, comparison, containment, case-insensitive substring, and regular-expression string requirements over JSON-serializable data object properties.
- Support nested property paths for object-valued data properties.
- Apply live-status filtering according to explicit query options.
- Support explicit query options for caller-supplied live-status overlays produced by a controller, knowledge-engineering tool, or other coordinating caller.
- Produce deterministic result bindings for matched anchors, links, and data objects.
- Apply a simple return processing specification to shape results.
- Return non-fatal query diagnostics for valid query specifications when useful, and raise declared query errors for malformed or unsupported specifications.

## Non-responsibilities

- Does not store RTG graph objects.
- Does not mutate RTG graph objects.
- Does not store or validate schema definitions.
- Does not store or execute constraint definitions.
- Does not infer new graph facts.
- Does not provide a general-purpose graph database query language.
- Does not own authorization, visibility, publication workflow, persistence, transport, or UI behavior.
- Does not decide whether a proposed graph change is valid.
- Does not call discovery or validation components when a query references unknown types or properties.

## Provided contracts

### `RtgQueryEngine.execute`

Kind:

- function

Inputs:

- `graph`
- `query_spec`
- `query_options`

Outputs:

- `RtgQueryResult`

Errors:

- `RtgQuerySpecInvalid`
- `RtgQueryUnsupported`

Semantics:

- Evaluates `query_spec` against the supplied graph read view through the public graph read contracts.
- The graph read view may be the live `component.rtg.graph` handle or any value that satisfies the public graph read contracts, such as a proposed or projected read view constructed by a validator or controller.
- Matches anchor buckets by anchor type.
- Matches typed directed links between named anchor buckets.
- Matches data requirements over data objects directly associated with matched anchors.
- Applies live-status filtering only when requested by `query_options`; by default, queries consider both live and non-live graph objects.
- May evaluate lifecycle filtering with a caller-supplied live-status overlay; this component does not read migration records or build migration projections itself.
- Returns deterministic result bindings and shaped return values.
- Does not mutate graph state.

### `RtgQuerySpec`

Kind:

- data structure

Fields:

- `anchor_buckets`
- `link_requirements`
- `data_requirements`
- `return_spec`
- `diagnostic_options`

Semantics:

- `anchor_buckets` names logical buckets and the anchor types each bucket may match.
- `link_requirements` names directed typed link requirements between buckets.
- `data_requirements` describes required associated data object types and property predicates for bucket matches.
- `return_spec` describes which matched anchors, links, data objects, and selected properties to return.
- `RtgQuerySpec` is the single canonical pattern representation; constraint definitions reference it as data rather than defining a parallel pattern language, and this component is its only evaluator.

### `RtgQueryAnchorBucket`

Kind:

- data structure

Fields:

- `name`
- `anchor_type_keys`

Semantics:

- Defines one named anchor match bucket.
- `name` is unique within one query spec and is used by link, data, and return requirements.
- `anchor_type_keys` is a non-empty ordered list of anchor type keys accepted for this bucket.

### `RtgQueryLinkRequirement`

Kind:

- data structure

Fields:

- `name`
- `source_bucket`
- `target_bucket`
- `link_type_keys`

Semantics:

- Requires a directed link from an anchor matched by `source_bucket` to an anchor matched by `target_bucket`.
- `name` is unique among link requirements within one query spec and is used by return specs.
- `source_bucket` and `target_bucket` must name existing anchor buckets.
- `link_type_keys` is a non-empty ordered list of accepted link types.
- A single anchor may satisfy more than one bucket; the engine does not require buckets to bind distinct anchors in v1.

### `RtgQueryDataRequirement`

Kind:

- data structure

Fields:

- `name`
- `anchor_bucket`
- `data_type_key`
- `required`
- `predicates`

Semantics:

- Matches data objects directly associated with anchors in `anchor_bucket`.
- `name` is unique among data requirements within one query spec and is used by return specs.
- `data_type_key` identifies the required associated data object type.
- `required` is a boolean; when true, bucket matches without a matching data object are rejected.
- `predicates` is an ordered list of `RtgQueryPropertyPredicate` records; all predicates must hold for the same candidate data object for it to match (logical AND).

### `RtgQueryPropertyPredicate`

Kind:

- data structure

Fields:

- `path`
- `operator`
- `value`
- `values`
- `case_sensitive`
- `regex_flags`

Semantics:

- `path` is an ordered list of property-name segments into a data object's JSON `properties` object.
- `operator` is one of `exists`, `equals`, `not_equals`, `lt`, `lte`, `gt`, `gte`, `contains`, `in`, `substring`, or `regex`.
- `value` is used by single-value operators such as `equals`, comparison, `contains`, `substring`, and `regex`.
- `values` is used by `in` and contains JSON-compatible scalar values.
- `exists` ignores `value` and `values`.
- `contains` tests array membership: the property must be an array that contains `value` by element equality.
- `in` tests scalar membership: the property value must equal one of `values`.
- `substring` performs case-insensitive partial string matching unless `case_sensitive` is true.
- `regex` searches string-valued properties for the pattern in `value` using a deterministic, linear-time regular-expression dialect (RE2-style: no backreferences or lookaround). `regex_flags` accepts only `case_insensitive` and `multiline` in v1; any other flag is rejected as `RtgQuerySpecInvalid`.
- Comparison operators `lt`, `lte`, `gt`, `gte` require both the property value and `value` to be the same ordered JSON kind (both numbers or both strings); any other combination is a non-match, not an error.
- `equals` and `not_equals` compare by JSON value: same kind and value matches, with numbers compared numerically; a cross-kind comparison is unequal.
- A `path` that does not resolve — a missing intermediate segment or an absent leaf — is a non-match for every operator except `exists`, which returns false; an unresolved path is never an error.

### `RtgQueryReturnSpec`

Kind:

- data structure

Fields:

- `anchor_buckets`
- `link_requirements`
- `data_requirements`
- `properties`

Semantics:

- Describes which matched records and selected property values appear in `RtgQueryResult.returns`.
- `anchor_buckets`, `link_requirements`, and `data_requirements` list names from the query spec.
- `properties` lists `(data_requirement_name, property_path)` pairs naming any property path on the matched data object to include in shaped returns; a selected path need not correspond to a predicate.
- Return specs shape output only; they do not change matching behavior.

### `RtgQueryDiagnosticOptions`

Kind:

- data structure

Fields:

- `include_non_fatal`
- `unknown_term_guidance`

Semantics:

- Controls query diagnostics without changing match results.
- `include_non_fatal` is a boolean; the default is `true`.
- `unknown_term_guidance` is `none` or `suggest_discovery`; the default is `suggest_discovery`.

### `RtgQueryOptions`

Kind:

- data structure

Fields:

- `live_filter`
- `live_status_overlay`
- `order_by`

Semantics:

- `live_filter` is `live`, `non_live`, `all`, or absent; absent means `all`.
- `live_status_overlay` is an optional mapping from graph object UUID to effective live status for the query.
- When supplied, `live_status_overlay` affects lifecycle filtering only; it does not mutate graph objects and does not change returned object records.
- The overlay is supplied by the caller or coordinating component; this component does not know or require its source.
- `order_by` is an optional ordered list of `RtgQueryOrderBy` records. Each record sorts rows by one returned property path.
- An `order_by` entry must reference a `(data_requirement, path)` pair listed in `return_spec.properties`.
- Ordering supports string and number property values. Missing, boolean, object, and array values sort last and do not make an otherwise valid query fail.
- Sorting is stable and applies after base UUID ordering, so equal sort values preserve deterministic component ordering.

### `RtgQueryOrderBy`

Kind:

- data structure

Fields:

- `data_requirement`
- `path`
- `direction`

Semantics:

- `data_requirement` names a data requirement included in `return_spec.properties`.
- `path` is the returned property path to sort by.
- `direction` is `ascending` or `descending`; absent means `ascending`.

### `RtgQueryResult`

Kind:

- data structure

Fields:

- `bindings`
- `returns`
- `diagnostics`

Semantics:

- `bindings` contains deterministic `RtgQueryBindingRow` values by query bucket and requirement name.
- `returns` contains deterministic `RtgQueryReturnRow` values aligned one-for-one with `bindings` by `row_index`.
- `diagnostics` contains `RtgQueryDiagnostic` records.
- Diagnostics are non-fatal guidance for valid query specifications, such as empty anchor buckets. Malformed query structure and unsupported operators or flags raise declared errors instead of returning diagnostics.

### `RtgQueryBindingRow`

Kind:

- data structure

Fields:

- `row_index`
- `anchors`
- `links`
- `data_objects`

Semantics:

- Represents one deterministic match combination.
- `row_index` is zero-based and assigned by the total result ordering defined below.
- `anchors` maps anchor bucket name to matched anchor UUID.
- `links` maps link requirement name to matched link UUID.
- `data_objects` maps data requirement name to matched data object UUID.
- When multiple links or data objects can satisfy a requirement, the query returns one row per deterministic match combination (the cross-product of independently satisfiable requirements).
- A required data requirement with no match rejects the row; an optional data requirement with no match is omitted from `data_objects` and does not suppress the row.
- Without `query_options.order_by`, rows are ordered by a total order over their bound UUIDs: compare matched anchor UUIDs in `anchor_buckets` declaration order, then matched link UUIDs in `link_requirements` declaration order, then matched data object UUIDs in `data_requirements` declaration order, each compared lexicographically by UUID string. An omitted optional `data_objects` slot sorts before any present UUID. With `order_by`, the base UUID order is the stable tie-breaker. `row_index` follows the final order.

### `RtgQueryReturnRow`

Kind:

- data structure

Fields:

- `row_index`
- `anchors`
- `links`
- `data_objects`
- `properties`

Semantics:

- Contains the shaped return data for the binding row with the same `row_index`.
- `anchors`, `links`, and `data_objects` contain only the names requested by `RtgQueryReturnSpec`.
- `properties` is a JSON-compatible object keyed by `data_requirement_name`; each value is a JSON object that mirrors the selected property paths structurally, so nested paths and segment names containing `.` are represented without delimiter ambiguity.
- Property values are copied from matched data object properties and are omitted when an optional data requirement has no matched data object or when the selected property path is absent.
- When a query returns rows but a requested return property resolves no values, diagnostics should identify whether the data requirement was unbound or the selected property path was absent on bound data objects.
- Return rows do not mutate or rewrite matched graph records.

### `RtgQueryDiagnostic`

Kind:

- data structure

Fields:

- `severity`
- `code`
- `message`
- `suggestion`
- `affected_terms`
- `diagnostic`

Semantics:

- Represents one query diagnostic.
- `severity` is `warning` or `info` for diagnostics returned in `RtgQueryResult`; malformed or unsupported query specs raise the declared errors instead of returning a result.
- `code` is a stable machine-readable diagnostic code.
- `message` states the query issue or note.
- `suggestion` gives concise caller-facing guidance when available.
- `affected_terms` lists query bucket names, requirement names, type keys, property paths, or predicate operators involved in the diagnostic.
- `diagnostic` is optional JSON-safe structured corrective guidance with fields such as `code`, `category`, `path`, `problem`, `remedy`, `accepted_fields`, `minimal_example`, and `guide_topics`.
- Query-owned diagnostics may teach query-shape and query-contract fixes, including returned property paths, `order_by` requirements, predicate operators, and bucket/requirement naming. They must not invoke discovery directly or include application-specific schema answers.
- Standard return-property diagnostic codes include `query.return_property_requirement_unbound` when a `return_spec.properties` entry names a data requirement with no row bindings, and `query.return_property_path_unresolved` when a bound data requirement exists but the selected property path resolves no values.

## Required contracts

May consume:

- Public read contracts from `component.rtg.graph`.
- JSON-serializable value and property-path conventions.

Must not consume:

- Graph storage internals from `component.rtg.graph`.
- Mutation APIs from `component.rtg.graph`.
- Schema, constraints, migration, controller, persistence, UI, authorization, or runtime orchestration components as required dependencies.

## Related components

- `component.rtg.controller` may expose query execution through its in-code API.
- `component.rtg.change_validation` consumes the query execution contract to evaluate query-shaped constraint patterns over a supplied read-view, while owning validation outcomes itself.
- `component.rtg.constraints` may store constraint definitions that reference this component's canonical `RtgQuerySpec` as data; `component.rtg.query` remains the single evaluator of those patterns, so there is no second pattern engine.

## Owned state

- None. This component derives query results from supplied graph state and query specifications.

## Invariants

### `invariant.rtg.query.no_mutation`

Query execution must not mutate graph state.

### `invariant.rtg.query.deterministic_results`

For the same graph state, query specification, and options, result ordering is deterministic.

### `invariant.rtg.query.deterministic_string_matching`

Substring and regular-expression matching are deterministic for the same graph state, query specification, and options. Regular-expression matching uses the linear-time RE2-style dialect and the restricted flag set defined by `RtgQueryPropertyPredicate`, so matching does not depend on a specific implementation's regex engine.

### `invariant.rtg.query.public_graph_reads_only`

The query engine uses only public graph read contracts.

### `invariant.rtg.query.operates_over_read_view`

The engine treats its graph input as a read view defined by the public graph read contracts. Callers may supply the live graph handle or a constructed read view, such as a proposed or projected view, without changing query behavior. The engine does not require the concrete `component.rtg.graph` implementation.

### `invariant.rtg.query.no_hidden_lifecycle_filter`

Live-status filtering is controlled by explicit query options and must not be hidden in implementation behavior.

### `invariant.rtg.query.overlay_filters_only`

Live-status overlays affect query lifecycle filtering but do not mutate graph state or rewrite returned graph object records.

### `invariant.rtg.query.default_includes_non_live`

When query options do not request lifecycle filtering, query execution considers both live and non-live graph objects.

### `invariant.rtg.query.discovery_independent`

Query execution does not call discovery components or schema search. When it can detect non-fatal lookup issues from graph reads, it may report diagnostics and lets controller or caller workflows decide whether to use discovery.

## Verification

Required checks:

- Boundary tests for anchor bucket matching by type.
- Boundary tests for directed typed link requirements between named buckets.
- Boundary tests for data existence and property predicates over associated data objects.
- Boundary tests for nested property paths.
- Boundary tests for case-insensitive substring and regular-expression string predicates.
- Boundary tests for return shaping.
- Boundary tests for live-status filtering options.
- Boundary tests proving callers can provide live-status overlays without query owning migration projection.
- Boundary tests proving empty bucket diagnostics and declared errors for malformed or unsupported query specs.
- Boundary tests proving unresolved returned property requirements and property paths produce non-fatal diagnostics.
- Side-effect tests proving query execution does not mutate graph state.
- Deterministic ordering tests.
- Result ordering tests proving `query_options.order_by` sorts by returned string or number property paths, keeps missing sort values last, and rejects non-returned sort paths.

Required evidence:

- A query can match a person bucket linked to a meeting bucket through an attended link.
- A query can require associated data object properties on matched anchors.
- A query can match nested data properties and partial string values.
- A query can return selected anchors and selected data properties.
- A query can explain empty returned-property objects without failing otherwise valid query results.
- Query execution does not require schema, constraints, migration, controller, or persistence components.
- Non-fatal query diagnostics can suggest controller discovery without directly invoking it.

## Change rules

Agents may:

- Add private query planning and matching helpers.
- Add supported predicate operators when documented in the query spec contract.
- Add boundary tests for new query features.

Agents may not:

- Add graph mutation behavior.
- Add graph object storage.
- Add schema or constraint storage.
- Fold validation, migration, controller, persistence, transport, authorization, or UI responsibilities into this component.
- Change accepted public contracts, owned state, invariants, or dependency rules without explicit human approval.

## Open questions

- What fuzzy matching algorithm and threshold options should a future query version use beyond v1 substring and regex matching?
