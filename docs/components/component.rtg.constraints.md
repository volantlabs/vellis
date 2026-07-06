---
id: component.rtg.constraints
type: Component
status: accepted
owner: humans
code:
  roots:
    - components/rtg/constraints
---

# RTG Constraints

## Purpose

Provide a constraint-definition store for RTG semantic graph-pattern rules, relationship requirements, cardinalities, and lifecycle-related rule definitions.

The component owns constraint records that higher-level validation and controller components consume. These records may describe required or optional connections, cardinalities, related anchor/data/link requirements, and value or range requirements across an object network. Constraint payloads reuse the RTG query pattern model where the semantics overlap. This component stores constraint definitions but does not execute those constraints against graph data.

## Responsibilities

- Store constraint definitions identified by stable UUID.
- Store live and non-live constraint definitions in the same registry.
- Store a display name on every constraint definition for navigation and audit readability.
- Store a plain-language description on every constraint definition so humans and agents can understand why the rule exists.
- Store a JSON-serializable `system` property store on every constraint definition.
- Store constraint payloads that describe semantic integrity requirements over RTG object networks, including cardinality rules that are too specific for schema definitions.
- Use the `RtgQuerySpec` pattern representation from `component.rtg.query` for anchor buckets, typed links, associated data requirements, and simple property predicates where those concepts overlap.
- Allow non-query-like constraints to use purpose-specific RTG constraint payloads when a pattern representation is not a good fit.
- Normalize missing `system.live` values to `true` and reject non-boolean `system.live` values.
- Maintain canonical UUID-to-constraint maps.
- Maintain derived indexes for lookup by constraint kind, target type key, and live status.
- Enforce structural integrity of constraint records as registry data.
- Generate constraint definition UUIDs for new constraint definitions, and accept caller-supplied UUIDs for special cases such as importing or relinking existing constraint definitions.
- Provide full-record write operations for constraint definitions.
- Provide read operations for direct lookup, listing by kind, listing by target type key, and listing by live status.
- Provide constraint snapshot import and export for callers that own persistence, replay, migration, testing, or storage adapters.

## Non-responsibilities

- Does not validate RTG graph objects or graph change batches.
- Does not execute constraints against `component.rtg.graph`.
- Does not inspect live RTG graph contents.
- Does not decide whether a constraint definition is compatible with the current schema or graph.
- Does not own schema definitions.
- Does not decide which constraints participate in a migration.
- Does not apply object changes to `component.rtg.graph`.
- Does not apply schema changes to `component.rtg.schema`.
- Does not own durable persistence, audit history, authorization, UI workflow, migration execution, or distributed coordination.
- Does not provide a general-purpose graph query language or inference engine.
- Does not own schema definition storage or direct schema compatibility enforcement.
- Does not store severity or blocking/non-blocking policy in v1 constraint definitions.
- Does not require display names, target type keys, or names to be unique in v1; UUIDs identify constraint definitions.

## Provided contracts

### `RtgConstraints.empty`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgConstraints`

Errors:

- None.

Semantics:

- Returns an empty in-memory constraint registry with no constraint definitions or derived indexes.

### `RtgConstraints.import_snapshot`

Kind:

- function

Inputs:

- `RtgConstraintSnapshot`

Outputs:

- `RtgConstraints`

Errors:

- `RtgConstraintSnapshotInvalid`
- `RtgConstraintUuidInvalid`
- `RtgConstraintUuidConflict`
- `RtgConstraintDefinitionInvalid`
- `RtgConstraintSystemValueInvalid`

Semantics:

- Builds an in-memory constraint registry from a JSON-serializable snapshot.
- Validates UUID uniqueness across constraint definitions.
- Normalizes missing `system.live` values to `true`.
- Validates that every resulting constraint `system.live` value is boolean.
- Validates constraint records as registry data.
- Rebuilds all derived indexes from canonical records.
- Does not execute constraints against graph data.

### `RtgConstraints.export_snapshot`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgConstraintSnapshot`

Errors:

- None.

Semantics:

- Returns a JSON-serializable snapshot of the current constraint registry state.
- The snapshot contains enough information to reconstruct an equivalent constraint registry through `RtgConstraints.import_snapshot`.
- Export does not inspect graph, schema, migration, or controller state.

### `RtgConstraints.put_constraint`

Kind:

- function

Inputs:

- `constraint`

Outputs:

- `RtgConstraintDefinition`

Errors:

- `RtgConstraintUuidInvalid`
- `RtgConstraintUuidConflict`
- `RtgConstraintKindInvalid`
- `RtgConstraintDefinitionInvalid`
- `RtgConstraintSystemValueInvalid`

Semantics:

- Creates a new constraint definition or fully replaces an existing constraint definition with the same UUID.
- When `constraint.uuid` is omitted, the component generates a new unique UUID and creates the constraint definition.
- When `constraint.uuid` is supplied, the component uses it unchanged to create or fully replace that constraint definition, which supports import and relinking workflows.
- `constraint.description` must explain the rule in plain language.
- Missing `constraint.system.live` defaults to `true`; supplied `constraint.system.live` must be boolean.
- The write does not execute the constraint and does not validate graph objects.
- Validates that `payload` is structurally well formed for `kind` — a `query_pattern` carries a well-formed `RtgConstraintQueryPatternPayload`, a `cardinality` carries a well-formed `RtgConstraintCardinalityPayload` — without evaluating or semantically checking the pattern; a `kind`/`payload` mismatch is rejected as `RtgConstraintDefinitionInvalid`.
- Indexes are updated atomically with the constraint record.

### `RtgConstraints.get_constraint`

Kind:

- function

Inputs:

- `constraint_uuid`

Outputs:

- `RtgConstraintDefinition`

Errors:

- `RtgConstraintNotFound`

Semantics:

- Returns one constraint definition by UUID.

### `RtgConstraints.list_constraints`

Kind:

- function

Inputs:

- `kind | None`
- `live | None`

Outputs:

- `RtgConstraintDefinitionList`

Errors:

- `RtgConstraintKindInvalid`

Semantics:

- Lists constraint definitions, optionally filtered by constraint kind and live status.
- Results are ordered deterministically for a given registry state.

### `RtgConstraints.list_constraints_by_target`

Kind:

- function

Inputs:

- `target_type_key`
- `live | None`

Outputs:

- `RtgConstraintDefinitionList`

Errors:

- `RtgConstraintTargetInvalid`

Semantics:

- Lists constraint definitions whose `target_type_keys` set contains `target_type_key`; a definition with several target keys is returned for each of them.
- The target key is registry metadata; this operation does not inspect schema or graph records.
- Results are ordered deterministically for a given registry state.

### `RtgConstraints.delete_constraint`

Kind:

- function

Inputs:

- `constraint_uuid`

Outputs:

- `RtgConstraintDeleteResult`

Errors:

- `RtgConstraintNotFound`

Semantics:

- Deletes one constraint definition from the registry.
- Does not alter graph objects, schema definitions, migrations, or validation results.

### `RtgConstraintDeleteResult`

Kind:

- data structure

Fields:

- `deleted_constraint`

Semantics:

- Represents the outcome of a constraint definition delete.
- `deleted_constraint` contains the full constraint definition record that was removed.
- This component does not cascade deletes into graph, schema, or migration records, so the result reports only the removed constraint definition.

### `RtgConstraintSnapshot`

Kind:

- data structure

Fields:

- `constraints`

Semantics:

- JSON-serializable constraint registry snapshot.
- `constraints` contains full constraint definition records with concrete UUIDs.
- Import validates the records and rebuilds derived indexes from them.

### `RtgConstraintDefinition`

Kind:

- data structure

Fields:

- `uuid`
- `kind`
- `target_type_keys`
- `display_name`
- `description`
- `payload`
- `system`

Semantics:

- Represents one stored RTG constraint definition.
- `uuid` is the constraint definition identity and may be omitted on write, in which case the component generates one.
- Returned, stored, deleted-result, and snapshot constraint definition records always contain a concrete UUID.
- `kind` is one of `query_pattern` or `cardinality` and selects the required payload type; an unrecognized `kind` is rejected as `RtgConstraintKindInvalid`.
- `target_type_keys` names schema type keys the constraint is primarily about for lookup and discovery.
- `display_name` is a human-readable label and is not required to be unique.
- `description` is a plain-language explanation of the rule.
- `payload` is JSON-serializable constraint data interpreted by validation components.
- Pattern-like constraints store `RtgConstraintQueryPatternPayload`.
- Cardinality constraints store `RtgConstraintCardinalityPayload`.
- Cardinality constraints, such as required associated data counts or link counts, belong in constraint payloads rather than schema definitions.
- In v1, violation of a live constraint definition means the validated graph or change is invalid.

### `RtgConstraintQueryPatternPayload`

Kind:

- data structure

Fields:

- `query_spec`
- `expectation`

Semantics:

- Represents a constraint that can be evaluated by executing an `RtgQuerySpec`-compatible pattern.
- `query_spec` uses the public query pattern representation from `component.rtg.query`.
- `expectation` is `must_match_at_least_one` or `must_match_none`.
- Validation components execute the query and decide whether the expectation is satisfied; this registry only stores the payload.

### `RtgConstraintCardinalityPayload`

Kind:

- data structure

Fields:

- `query_spec`
- `counted_binding`
- `minimum`
- `maximum`

Semantics:

- Represents a cardinality constraint evaluated over query result bindings.
- `query_spec` selects the relevant anchor, link, or data-object bindings.
- `counted_binding` names an anchor bucket, link requirement, or data requirement in the query spec.
- `minimum` and `maximum` are non-negative integers or absent; at least one is present.
- Validation components count deterministic query binding rows for `counted_binding` and compare that count to the supplied bounds.

### `RtgConstraintDefinitionList`

Kind:

- data structure

Fields:

- `constraints`

Semantics:

- Ordered list wrapper for constraint definition records.
- `constraints` contains full `RtgConstraintDefinition` records with concrete UUIDs.

## Required contracts

May consume:

- JSON-serializable value conventions for snapshots, constraint payloads, and system metadata.
- RTG type-key naming conventions when constraint targets are expressed as type keys.
- `RtgQuerySpec` pattern conventions from `component.rtg.query` when constraint payloads use query-like graph patterns.

Must not consume:

- Live graph storage internals from `component.rtg.graph`.
- Schema registry internals from `component.rtg.schema`.
- Migration internals from `component.rtg.migration`.
- Query, validation, controller, persistence, UI, authorization, or runtime orchestration components.

## Related components

- `component.rtg.change_validation` may consume live constraint definitions to validate RTG change batches.
- `component.rtg.controller` may write constraint definitions and include constraints in system snapshots.
- `component.rtg.migration` may reference constraint definitions when a migration changes which constraints are live.
- `component.rtg.schema` owns object-level schema definition records that constraint definitions may reference by type key.
- `component.rtg.query` owns query execution over graph state; this component may share compatible pattern data but does not execute queries.

## Owned state

- Constraint definition records.
- Constraint UUID namespace.
- Constraint-kind indexes.
- Constraint-target indexes.
- Live-status indexes.

## Invariants

### `invariant.rtg.constraints.uuid_unique`

Each UUID identifies at most one constraint definition.

### `invariant.rtg.constraints.display_name_not_identity`

Constraint display names are labels for navigation and audit readability; they do not identify constraint definitions and are not unique in v1.

### `invariant.rtg.constraints.live_status_boolean`

Every constraint definition has a boolean `system.live` value after normalization.

### `invariant.rtg.constraints.no_validation_execution`

The component stores constraint definitions but never reports whether graph data satisfies them.

### `invariant.rtg.constraints.cardinality_rules_live_here`

Cardinality beyond schema-level required versus optional field or association presence is represented by constraint definitions.

### `invariant.rtg.constraints.no_severity_policy_v1`

V1 constraint definitions do not carry severity or blocking/non-blocking policy; validation treats live constraint violations as invalid.

### `invariant.rtg.constraints.pattern_compatibility`

Constraint definitions that express query-like graph patterns use the `RtgQuerySpec` pattern representation from `component.rtg.query` unless a purpose-specific constraint payload is required.

### `invariant.rtg.constraints.indexes_match_records`

Derived indexes match canonical constraint records after every successful mutation and import.

## Verification

Required checks:

- Boundary tests for empty registry creation.
- Boundary tests for adding, replacing, retrieving, listing, exporting, and importing constraint definitions.
- Boundary tests for UUID conflict rejection.
- Boundary tests proving writes without a supplied UUID receive a generated unique UUID, and writes with a supplied UUID use it unchanged.
- Boundary tests proving display names are preserved and not treated as unique identifiers.
- Boundary tests for `system.live` defaulting and boolean validation.
- Boundary tests proving constraint definitions can be listed by kind, target, and live status.
- Boundary tests for descriptions and pattern-like constraint payload structure.
- Boundary tests proving cardinality rules can be stored without executing them.
- Boundary tests proving v1 constraint definitions do not expose severity policy fields.
- API-surface checks proving constraint execution is not exposed by this component.

Required evidence:

- A consumer can store live and non-live constraint definitions.
- A consumer can retrieve constraint definitions without reading graph or schema state.
- A consumer can store a cardinality constraint that validation may later execute.
- The component does not accept graph objects as validation inputs.

## Change rules

Agents may:

- Change private storage and indexing of constraint definitions.
- Add constraint metadata fields when they remain definition data.
- Add boundary tests for registry behavior.
- Refactor snapshot import and export.

Agents may not:

- Add graph validation execution APIs.
- Add schema definition storage.
- Add graph object storage.
- Read or mutate RTG graph objects.
- Fold validator, query, migration, persistence, controller, or UI responsibilities into this component.
- Change accepted public contracts, owned state, invariants, or dependency rules without explicit human approval.

## Open questions

- None.
