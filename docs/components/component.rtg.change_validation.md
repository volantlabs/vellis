---
id: component.rtg.change_validation
type: Component
status: accepted
owner: humans
code:
  roots:
    - components/rtg/change_validation
---

# RTG Change Validation

## Purpose

Validate requested RTG change batches against current graph state, schema definitions, constraint definitions, and migration records without mutating any source component.

The component is the boundary for deciding whether a proposed batch is structurally and semantically admissible before a controller applies it. It remains one public component for now, with internally isolated validation tracks that can later split into narrower validator components if the contracts justify it.

## Responsibilities

- Accept RTG change batches containing proposed graph object, schema definition, constraint definition, migration-record, delete, and lifecycle operations.
- Build validation views from current graph, schema, constraints, and migration state plus the proposed batch sections relevant to each track.
- Run a schema/object validation track for individual RTG object integrity against applicable schema definitions.
- Run a constraint/network validation track for semantic graph integrity, constraint-definition schema compatibility, and constraint-definition admissibility against applicable constraint definitions.
- Evaluate query-shaped constraint patterns by delegating to `component.rtg.query` over a read-view of the relevant graph state rather than reimplementing pattern matching.
- Run a migration/cutover validation track for migration-record admissibility and lifecycle-transition sanity checks.
- Validate referential closure of proposed graph changes against current graph state.
- Use graph delete and dissociation preview contracts to validate the projected post-delete state of proposed deletes and dissociations before they are applied.
- Validate lifecycle requirements for proposed live/non-live transitions when supplied in the batch or migration record.
- Validate proposed constraint definitions against the schema definitions they reference before a controller writes them.
- Validate current live graph state and projected post-migration state when callers provide the corresponding validation inputs.
- Validate actual post-apply and post-cutover graph, schema, and constraint state when the controller supplies the mutated component views.
- Return deterministic validation reports with track-labeled findings, errors, warnings, affected UUIDs, concise fix guidance, and evidence metadata.
- Return all deterministic findings practical for the requested validation scope rather than stopping at the first blocking finding.
- Preserve input graph, schema, constraint, and migration state without side effects.

## Non-responsibilities

- Does not store graph objects.
- Does not store schema definitions.
- Does not store constraint definitions.
- Does not store migration records.
- Does not apply accepted changes to `component.rtg.graph`.
- Does not mutate `component.rtg.schema`, `component.rtg.constraints`, or `component.rtg.migration`.
- Does not own publication, migration cutover, authorization, UI workflow, persistence, or distributed coordination.
- Does not provide general query results beyond validation evidence.

## Provided contracts

### `RtgChangeValidator.validate_batch`

Kind:

- function

Inputs:

- `graph`
- `schema`
- `constraints`
- `migration | None`
- `query`
- `change_batch`
- `validation_options`

Outputs:

- `RtgValidationReport`

Errors:

- `RtgValidationInputInvalid`

Semantics:

- Validates `change_batch` against the supplied graph, schema, constraint, and optional migration components.
- `change_batch` is an `RtgChangeBatch`; `graph`, `schema`, `constraints`, and `migration` are read views satisfying the corresponding components' public read contracts; `query` is the query execution contract.
- Raises `RtgValidationInputInvalid` only for unusable inputs — a missing required component view or a structurally malformed batch envelope, such as a reference carrying neither `resource_id` nor `local_ref`. Domain rule violations, including a well-formed reference that targets a nonexistent resource, are returned as findings rather than raised.
- Uses graph reads to resolve existing anchors, data objects, links, associations, and incident links.
- Uses schema reads to resolve live or explicitly selected schema definitions.
- Uses constraint reads to resolve live or explicitly selected constraint definitions.
- Evaluates query-shaped constraint patterns by calling `component.rtg.query` over a read-view of the current and proposed graph state.
- Uses migration reads only for migration-record changes or migration-aware validation options.
- Treats the batch as proposed data and does not mutate graph, schema, constraints, or migration state.
- Builds proposed graph, schema, constraint, and migration views from the corresponding `RtgChangeBatch` sections instead of assuming all proposed state is graph state.
- Validates migration cutover by receiving a change batch derived from the migration record and running the migration/cutover track.
- When a batch writes migration records, validates those new records' projected cutover states against the proposed graph, schema, constraint, and migration views before reporting the batch accepted.
- Runs only the validation tracks requested by `validation_options`; default options run all tracks relevant to the batch.
- Produces findings according to the Validation rules catalog below; blocking findings prevent acceptance.
- Reports all deterministic findings unless validation options provide an explicit finding limit.
- Returns a report containing success/failure, validation findings, affected UUIDs, and evidence metadata.

### `RtgChangeValidator.validate_graph_state`

Kind:

- function

Inputs:

- `graph`
- `schema`
- `constraints`
- `migration | None`
- `query`
- `migration_ids | None`
- `validation_options`

Outputs:

- `RtgValidationReport`

Errors:

- `RtgValidationInputInvalid`

Semantics:

- Validates the supplied graph, schema, and constraint views against each other as they stand; the caller decides whether those views are the current live state or an already-mutated post-cutover state, and validation behavior is identical in both cases.
- When one or more `migration_ids` are supplied, validation builds projected graph, schema, and constraint validation views from the corresponding migration cutover plans in caller-supplied order, then validates the projected post-migration state.
- Inputs follow the same typing as `validate_batch`; `migration_ids` selects migrations from the supplied migration view.
- Does not mutate graph, schema, constraints, or migration state.
- Returns all deterministic violations found for the requested scope.
- Honors caller-supplied finding limits when validation options specify them.

### `RtgChangeBatch`

Kind:

- data structure

Fields:

- `graph_changes`
- `schema_changes`
- `constraint_changes`
- `migration_changes`

Semantics:

- `graph_changes` is an `RtgGraphChangeSet`, `schema_changes` is an `RtgSchemaChangeSet`, `constraint_changes` is an `RtgConstraintChangeSet`, and `migration_changes` is an `RtgMigrationChangeSet`. These change-set types are the single representation of proposed operations; the batch does not redefine them.
- The batch is a normalized validation, replay, and controller-internal planning representation. It is not required to be the primary human- or agent-facing controller write workflow.
- Empty or absent sections are valid and mean that no changes are proposed for that resource category.
- New resources may carry a batch-local reference so other operations in the same batch can target them before concrete IDs are assigned; the controller resolves these references to concrete resource IDs, and validation treats a batch-local reference as the identity of the proposed new resource.
- Within one batch, the same resolved resource must not appear in more than one mutation category for its resource type, except that graph association changes may reference graph objects created by graph write operations in the same batch.
- Proposed graph, schema, constraint, and migration read views are interpreted deterministically in this order: writes, association additions, dissociations, deletes, then live-status changes, with migration status and evidence changes applied after migration writes.
- Validation tracks must read only the sections needed for their declared scope and must report findings against the section that introduced the proposed state.

### `RtgChangeReference`

Kind:

- data structure

Fields:

- `resource_id`
- `local_ref`

Semantics:

- Identifies an existing or proposed resource inside a change batch.
- Exactly one of `resource_id` or `local_ref` is present.
- `resource_id` identifies an existing resource or caller-supplied concrete identity; it is a UUID for graph, schema, and constraint resources and a migration ID for migration resources.
- `local_ref` is unique within one `RtgChangeBatch` and lets later operations refer to a proposed resource before the controller resolves it to a concrete resource ID.
- Validation reports findings against these references so callers can repair the original batch.

### `RtgGraphChangeSet`

Kind:

- data structure

Fields:

- `anchor_writes`
- `data_object_writes`
- `link_writes`
- `associate_data`
- `dissociate_data`
- `delete_anchors`
- `delete_data_objects`
- `delete_links`
- `set_live`

Semantics:

- Contains only graph-state changes proposed by the batch.
- Write entries use batch operation records so endpoints and anchor associations may refer to batch-local references.
- Delete entries contain `RtgChangeReference` values.
- `set_live` changes only the `system.live` value of existing or same-batch graph records in the proposed view.
- Validation uses graph preview contracts for dissociation and delete cascade effects when building the projected post-change graph view.

### `RtgGraphAnchorWrite`

Kind:

- data structure

Fields:

- `ref`
- `type`
- `display_name`
- `system`

Semantics:

- Proposes creating or fully replacing an anchor.
- `ref` identifies the anchor by concrete UUID or batch-local reference.
- `system` is the proposed full system metadata after write; missing `system.live` is interpreted by the graph component default.

### `RtgGraphDataObjectWrite`

Kind:

- data structure

Fields:

- `ref`
- `type`
- `properties`
- `system`
- `anchor_refs`

Semantics:

- Proposes creating or fully replacing a data object and its direct anchor associations.
- `anchor_refs` is a non-empty ordered list of `RtgChangeReference` values and replaces the data object's direct anchor associations in the proposed view.

### `RtgGraphLinkWrite`

Kind:

- data structure

Fields:

- `ref`
- `type`
- `source_ref`
- `target_ref`
- `system`

Semantics:

- Proposes creating or fully replacing a typed link.
- `source_ref` and `target_ref` identify the proposed link endpoints and may target same-batch anchor or data-object writes.
- The controller resolves endpoint references to concrete UUIDs before calling the graph write contract.

### `RtgGraphAssociationChange`

Kind:

- data structure

Fields:

- `anchor_ref`
- `data_ref`

Semantics:

- Represents one direct anchor-data association addition or dissociation.
- The association itself has no UUID, type, properties, or system metadata.

### `RtgGraphLiveStatusChange`

Kind:

- data structure

Fields:

- `object_ref`
- `live`

Semantics:

- Proposes replacing only the `system.live` value of an anchor, data object, or link in the projected graph view.
- Validation treats other `system` keys and domain properties as unchanged.

### `RtgSchemaChangeSet`

Kind:

- data structure

Fields:

- `definition_writes`
- `delete_definitions`
- `set_live`

Semantics:

- Contains proposed schema definition writes, deletes, and live-status changes.
- `definition_writes` contains `RtgSchemaDefinitionWrite` records.
- `delete_definitions` contains `RtgChangeReference` values.
- `set_live` contains definition references and target boolean live values.

### `RtgSchemaDefinitionWrite`

Kind:

- data structure

Fields:

- `ref`
- `definition`

Semantics:

- Proposes creating or fully replacing one schema definition.
- `ref` identifies the definition by concrete UUID or batch-local reference.
- `definition.uuid` may be absent when `ref.local_ref` is present; after controller resolution, `definition.uuid` is concrete before the schema component is called.

### `RtgConstraintChangeSet`

Kind:

- data structure

Fields:

- `constraint_writes`
- `delete_constraints`
- `set_live`

Semantics:

- Contains proposed constraint definition writes, deletes, and live-status changes.
- `constraint_writes` contains `RtgConstraintDefinitionWrite` records.
- `delete_constraints` contains `RtgChangeReference` values.
- `set_live` contains constraint references and target boolean live values.

### `RtgConstraintDefinitionWrite`

Kind:

- data structure

Fields:

- `ref`
- `constraint`

Semantics:

- Proposes creating or fully replacing one constraint definition.
- `ref` identifies the constraint definition by concrete UUID or batch-local reference.
- `constraint.uuid` may be absent when `ref.local_ref` is present; after controller resolution, `constraint.uuid` is concrete before the constraints component is called.

### `RtgMigrationChangeSet`

Kind:

- data structure

Fields:

- `migration_writes`
- `delete_migrations`
- `status_changes`
- `evidence_additions`

Semantics:

- Contains proposed migration record writes, deletes, status changes, and evidence additions.
- `migration_writes` contains `RtgMigrationRecordWrite` records.
- `delete_migrations` contains `RtgChangeReference` values.
- `status_changes` and `evidence_additions` target migration records by `RtgChangeReference`.

### `RtgMigrationRecordWrite`

Kind:

- data structure

Fields:

- `ref`
- `migration`

Semantics:

- Proposes creating or fully replacing one migration record.
- `ref` identifies the migration by concrete migration ID or batch-local reference.
- `migration.migration_id` may be absent when `ref.local_ref` is present; after controller resolution, `migration.migration_id` is concrete before the migration component is called.

### `RtgLiveStatusChange`

Kind:

- data structure

Fields:

- `target_ref`
- `live`

Semantics:

- Reusable live-status operation for schema and constraint definitions.
- The operation changes only `system.live` in the proposed view.

### `RtgMigrationStatusChange`

Kind:

- data structure

Fields:

- `migration_ref`
- `status`
- `status_metadata`

Semantics:

- Proposes a migration status transition and caller-supplied status metadata.
- Validation checks the transition against the migration component's status-transition contract.

### `RtgMigrationEvidenceAddition`

Kind:

- data structure

Fields:

- `migration_ref`
- `evidence`

Semantics:

- Proposes appending one evidence record to a migration.
- The evidence shape is owned by `component.rtg.migration`; validation treats it as migration data and does not re-run referenced evidence.

### `RtgValidationOptions`

Kind:

- data structure

Fields:

- `tracks`
- `finding_limit`

Semantics:

- Controls validation scope and report size.
- `tracks` is `all` or a list containing `schema_object`, `constraint_network`, or `migration_cutover`; the default is `all`.
- `finding_limit` is a positive integer or absent; when absent, validation returns all deterministic findings practical for the requested scope.
- `finding_limit` limits returned findings only; acceptance is computed from every finding produced by the executed tracks before limiting.
- Track selection changes which checks execute, but it does not allow executed tracks to ignore blocking findings.

### `RtgValidationFinding`

Kind:

- data structure

Fields:

- `track`
- `severity`
- `code`
- `message`
- `suggestion`
- `affected_references`
- `diagnostic`

Semantics:

- `track` identifies the validation track that produced the finding, such as `schema_object`, `constraint_network`, or `migration_cutover`.
- `severity` identifies whether the finding is blocking, warning, or informational.
- `code` is a stable machine-readable finding code drawn from the Validation rules catalog; each code has a fixed track and severity.
- `message` states exactly what is wrong.
- `suggestion` gives concise agent-facing guidance for how to proceed, such as using discovery to find valid types or properties.
- `affected_references` identifies the graph, schema, constraint, migration, or batch-section references involved in the finding.
- `diagnostic` is optional JSON-safe structured corrective guidance with fields such as `code`, `category`, `path`, `problem`, `remedy`, `guide_topics`, `safe_to_retry`, and `mutation_state`.
- Diagnostics are generic and component-owned: validation findings may teach schema/object repair, reference resolution, link endpoint repair, and migration-cutover validation remediation, but they must not contain application-specific answer keys.

### `RtgValidationReport`

Kind:

- data structure

Fields:

- `accepted`
- `findings`
- `evidence`

Semantics:

- `accepted` is true only when executed validation tracks found no blocking findings.
- `findings` is the canonical deterministic list of validation findings; when a finding limit is requested, blocking findings are returned before warnings or informational findings.
- Reports include all deterministic findings by default; callers may request a maximum finding count through validation options.
- `evidence` contains caller-consumable metadata that migration or controller components may record, including returned finding count, total produced finding count, and whether the report was truncated.

## Validation rules

Each track maps specific conditions to findings with a stable `code` and a `severity`. Severity follows one policy across all tracks: structural, shape, reference, lifecycle, and constraint violations that would leave invalid state are `blocking`; advisory quality or discoverability notes are `warning`; purely explanatory notes are `informational`. Only `blocking` findings set `accepted` to false. The codes below are the v1 catalog; agents may add codes for new conditions but may not change the severity of an existing code without approval.

### Schema/object track (`schema_object`)

Evaluates each proposed and current graph object in the projected view against the live or batch-selected schema definition for its type, using `component.rtg.schema` reads. A graph object's `type` is matched to a schema `type_key`.

- `schema_object.unknown_type` (blocking): a graph object's type has no matching live or batch-selected schema definition.
- `schema_object.undeclared_property` (blocking): a data object carries a property not declared by its `RtgDataObjectSchemaPayload` when that payload is strict.
- `schema_object.property_kind_mismatch` (blocking): a property's value kind is not permitted by the schema field's `value_kinds`.
- `schema_object.missing_required_property` (blocking): a strict data object omits a required declared property.
- `schema_object.missing_required_associated_data` (blocking): an anchor lacks an association required by its `RtgAnchorSchemaPayload` required data types.
- `schema_object.link_endpoint_type_invalid` (blocking): a link's source or target type is not permitted by its `RtgLinkSchemaPayload` allowed source or target types.
- `schema_object.reference_missing` (blocking): a graph change references an anchor or data object that is neither present in current graph state nor written in the same batch; findings include the request path and repair guidance.

### Constraint/network track (`constraint_network`)

Evaluates live or batch-selected constraint definitions against the projected graph view, and checks proposed constraint definitions for admissibility. Query-shaped patterns are evaluated by delegating to `component.rtg.query`.

- `constraint_network.pattern_unsatisfied` (blocking): a `query_pattern` constraint's `expectation` (`must_match_at_least_one` or `must_match_none`) is not met when its `query_spec` is evaluated through `component.rtg.query` over the projected read-view.
- `constraint_network.cardinality_out_of_bounds` (blocking): a `cardinality` constraint's counted-binding count falls outside `minimum`/`maximum`.
- `constraint_network.constraint_target_unknown` (blocking): a proposed constraint's `target_type_keys` or pattern type keys reference a type key with no live or batch-selected schema definition. This is the `constraint_schema_compatibility` check.
- `constraint_network.constraint_payload_unevaluable` (blocking): a proposed constraint payload cannot be evaluated against the schema, for example a `counted_binding` that names no binding present in its `query_spec`.

### Migration/cutover track (`migration_cutover`)

Evaluates proposed migration records and projected cutover effects using `component.rtg.migration` reads.

- `migration_cutover.reference_missing` (blocking): a migration make-live, make-non-live, or replacement entry references a resource absent from the projected view.
- `migration_cutover.wrong_live_state` (blocking): a make-live entry references an already-live record, or a make-non-live entry references an already-non-live record, in the projected view.
- `migration_cutover.invalid_status_transition` (blocking): a proposed `RtgMigrationStatusChange` is not permitted by the migration component's status-transition contract.
- `migration_cutover.post_state_invalid` (blocking): the projected post-cutover state fails one or more schema/object or constraint/network checks above.
- `migration_cutover.replacement_type_mismatch` (warning): an old-to-new replacement maps records of differing types, which is permitted but surfaced for review.

Findings for unknown types, undeclared properties, or unknown pattern terms include a `suggestion` to use controller discovery to find valid type keys and properties.

## Required contracts

May consume:

- Public read contracts from `component.rtg.graph`, including its non-mutating delete and dissociation preview contracts.
- Public read contracts from `component.rtg.schema`.
- Public read contracts from `component.rtg.constraints`.
- Public read contracts from `component.rtg.migration` when validating migration-related change batches.
- The public query execution contract from `component.rtg.query` to evaluate query-shaped constraint patterns over current, proposed, and projected read-views.

Must not consume:

- Storage internals from graph, schema, constraints, or migration components.
- Graph, schema, constraint, or migration mutation APIs.
- Persistence, UI, authorization, transport, or runtime orchestration components.

## Related components

- `component.rtg.controller` may invoke this component before applying RTG change batches or migration cutover, and owns mutation sequencing after validation succeeds.
- `component.rtg.migration` may store validation evidence emitted by this component.
- `component.rtg.query` evaluates query-shaped constraint patterns for the constraint/network track over a supplied read-view; this component owns the validation outcomes derived from those matches.

## Owned state

- None. This component derives validation reports from supplied components and request data.

## Invariants

### `invariant.rtg.change_validation.no_mutation`

Validation must not mutate graph, schema, constraint, or migration state.

### `invariant.rtg.change_validation.deterministic_reports`

For the same input states, batch, and options, validation findings are deterministic.

### `invariant.rtg.change_validation.findings_are_comprehensive`

Validation returns all deterministic findings for the requested scope unless a caller-supplied finding limit is present. Limited reports expose truncation metadata so callers can distinguish "no more findings" from "more findings omitted."

### `invariant.rtg.change_validation.source_of_truth_external`

The component does not own graph objects, schema definitions, constraint definitions, or migration records.

### `invariant.rtg.change_validation.blocking_findings_control_acceptance`

Reports are accepted only when no blocking findings are present across all findings produced by the executed tracks. Report-size limiting must not hide a blocking finding from `accepted`.

### `invariant.rtg.change_validation.findings_are_agent_actionable`

Validation findings include exact issue descriptions and concise remediation guidance suitable for agent consumers.

### `invariant.rtg.change_validation.tracks_are_extractable`

Validation tracks communicate through explicit validation inputs, options, track-labeled findings, and shared read-only views only. A track must not rely on private state from another track, so schema/object, constraint/network, or migration/cutover validation can become separate components without changing report semantics.

### `invariant.rtg.change_validation.batch_sections_explicit`

Proposed graph, schema, constraint, and migration state must have one representation in validation inputs and must remain distinguishable in validation findings.

### `invariant.rtg.change_validation.constraint_schema_compatibility`

Proposed constraint definitions are checked against referenced schema definitions before controller writes them.

### `invariant.rtg.change_validation.pattern_eval_delegated_to_query`

Query-shaped constraint patterns are evaluated by delegating to `component.rtg.query` over a read-view of the relevant graph state. The component does not reimplement graph pattern matching. Non-pattern, purpose-specific constraint payloads may be evaluated by the component directly.

### `invariant.rtg.change_validation.cascade_effects_from_graph_preview`

Validation does not re-implement the graph delete-cascade or data-object grounding mechanics owned by `component.rtg.graph`. It obtains delete and dissociation cascade effects through the graph's non-mutating preview contracts and validates the projected post-delete state before changes are applied. Projected migration state is represented as validation-only graph, schema, and constraint views derived from migration cutover plans.

## Verification

Required checks:

- Boundary tests for accepted and rejected RTG change batches.
- Boundary tests for object-shape validation using schema definitions.
- Boundary tests for multi-object constraint validation using constraint definitions.
- Boundary tests proving query-shaped constraint violations are detected by delegating to `component.rtg.query` over current and proposed read-views.
- API-surface checks proving the component does not reimplement graph pattern matching.
- Boundary tests for constraint-definition schema compatibility before controller writes.
- Boundary tests for migration/cutover validation using migration records.
- Boundary tests proving staged migration records are validated against their projected cutover state in the same batch.
- Boundary tests for validating current live graph state.
- Boundary tests for validating projected post-migration state from one or more migration IDs.
- Boundary tests for validating actual applied post-cutover state from already-mutated graph, schema, and constraint views.
- Boundary tests proving undeclared data object properties and unknown schema types are blocking findings.
- Boundary tests proving schema, constraint, and migration batch sections are validated without being treated as graph mutations.
- Boundary tests for referential closure across current graph state plus proposed changes.
- Boundary tests proving proposed deletes and dissociations are validated against the graph preview cascade set without mutating the graph.
- Boundary tests proving validation tracks can run independently through validation options.
- Boundary tests proving validation does not mutate graph, schema, constraints, or migration.
- Deterministic report ordering tests.
- Tests proving multiple independent blocking findings are returned in one report where practical.
- Tests proving all deterministic findings are returned by default and caller-supplied finding limits are honored.
- Tests proving caller-supplied finding limits cannot cause blocking findings to be accepted or hidden behind lower-severity findings.
- Tests proving findings include remediation guidance.

Required evidence:

- A malformed object batch is rejected without graph mutation.
- A graph-pattern constraint violation is reported with affected UUIDs.
- A migration cutover with missing or wrong-state references is rejected without changing migration status.
- A query or validation request that names an unknown type or property suggests discovery as the next corrective step.

## Change rules

Agents may:

- Add private validation helpers and rule evaluators.
- Add finding codes and evidence fields when they remain validation-report data.
- Refactor internal validation tracks when the public report contract and no-mutation invariant are preserved.
- Add boundary tests for new validation behavior.

Agents may not:

- Add graph, schema, constraint, or migration storage.
- Mutate source components.
- Make one validation track depend on private implementation state from another track.
- Fold controller, persistence, UI, transport, or authorization responsibilities into this component.
- Change accepted public contracts, owned state, invariants, or dependency rules without explicit human approval.

## Open questions

- When should schema/object, constraint/network, or migration/cutover validation split into separate validator components?
