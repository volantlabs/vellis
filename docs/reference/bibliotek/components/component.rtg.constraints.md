# component.rtg.constraints

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgConstraints`
- Lifecycle: `accepted`
- Purpose: Own declarative constraint records and derived kind/target/live indexes, while evaluation remains with validation/query consumers.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `exportSnapshot` | `ExportConstraintSnapshot` | out `snapshot: RtgConstraintSnapshot` | None | Export every full constraint record without evaluating it or inspecting other components. |
| `putConstraint` | `PutConstraint` | in `constraint: RtgConstraintDefinition`; out `stored: RtgConstraintDefinition` | `RtgConstraintUuidInvalid`, `RtgConstraintUuidConflict`, `RtgConstraintKindInvalid`, `RtgConstraintDefinitionInvalid`, `RtgConstraintPayloadInvalid`, `RtgConstraintSystemValueInvalid` | Generate or preserve identity, validate kind-specific structure and bounds, and atomically create or fully replace one record. A kind/payload type mismatch is RtgConstraintDefinitionInvalid; malformed contents of the selected payload are RtgConstraintPayloadInvalid. |
| `getConstraint` | `GetConstraint` | in `constraintUuid: Uuid`; out `constraint: RtgConstraintDefinition` | `RtgConstraintNotFound` | Return one full constraint definition by UUID without executing it. |
| `listConstraints` | `ListConstraints` | in `kind: RtgConstraintKind[0..1]`; in `live: Boolean[0..1]`; out `result: RtgConstraintDefinitionList` | `RtgConstraintKindInvalid` | List definitions with optional kind/live filters in deterministic order. |
| `listConstraintsByTarget` | `ListConstraintsByTarget` | in `targetTypeKey: String`; in `kind: RtgConstraintKind[0..1]`; in `live: Boolean[0..1]`; out `result: RtgConstraintDefinitionList` | `RtgConstraintTargetInvalid`, `RtgConstraintKindInvalid` | List definitions whose target metadata contains one type key, optionally filtered by constraint kind and live status. |
| `deleteConstraint` | `DeleteConstraint` | in `constraintUuid: Uuid`; out `result: RtgConstraintDeleteResult` | `RtgConstraintNotFound` | Delete exactly one definition without cascading into graph, schema, migration, or validation state. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgConstraints` | out `constraints: RtgConstraints` | None | Return an empty registry with empty derived indexes. |
| `ImportRtgConstraintSnapshot` | in `snapshot: RtgConstraintSnapshot`; out `constraints: RtgConstraints` | `RtgConstraintSnapshotInvalid`, `RtgConstraintUuidInvalid`, `RtgConstraintUuidConflict`, `RtgConstraintKindInvalid`, `RtgConstraintDefinitionInvalid`, `RtgConstraintPayloadInvalid`, `RtgConstraintSystemValueInvalid` | Validate all identities, records, payloads, bounds, and system values before rebuilding indexes and exposing the registry. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `constraintRecords` | `RtgConstraintDefinition` | `owned` | Canonical component-owned constraint-definition occurrences. |
| `derivedIndexes` | `JsonObject` | `derived` | Ephemeral indexes derived from canonical constraint definitions. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `exportSnapshot` | `constraintRecords` | `read` | read all canonical records. |
| `putConstraint` | `constraintRecords` | `write` | atomically create/replace one record and rebuild affected indexes. |
| `getConstraint` | `constraintRecords` | `read` | read one canonical record. |
| `listConstraints` | `derivedIndexes` | `read` | read kind/live indexes. |
| `listConstraintsByTarget` | `derivedIndexes` | `read` | read target/kind/live indexes. |
| `deleteConstraint` | `constraintRecords` | `delete` | remove one record and affected indexes. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.constraints.write_effect` | `PutConstraint` | `registry.putConstraint` | Missing UUID generates identity; supplied identity is preserved. Kind selects a compatible typed payload, target keys are unique and unordered, descriptions remain human-readable, missing live becomes true, and writes do not execute rules. Duplicate target keys are rejected rather than silently repaired. |
| `contract.rtg.constraints.read_effect` | `RtgConstraints` | `registry` | Reads honor explicit filters, use ascending textual constraint UUID order, derive only from canonical records/indexes, and never inspect or mutate graph/schema state. |
| `contract.rtg.constraints.delete_effect` | `DeleteConstraint` | `registry.deleteConstraint` | Delete removes exactly one definition and index entries with no cross-component cascade. |
| `contract.rtg.constraints.snapshot_effect` | `RtgConstraints` | `registry` | Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. |
| `contract.rtg.constraints.intentional_boundary` | `RtgConstraints` | `registry` | This registry owns declarative definitions only. It does not execute constraints, inspect or mutate graph/schema/migration state, choose migration membership, own durable persistence or workflow, provide general graph query/inference, or attach v1 severity/blocking policy. UUID alone identifies a definition; names and target keys may be shared by multiple definitions. |
| `invariant.rtg.constraints.uuid_unique` | `RtgConstraints` | `registry` | Constraint UUIDs are unique. |
| `invariant.rtg.constraints.display_name_not_identity` | `RtgConstraints` | `registry` | Display name is non-unique navigation text, not identity. |
| `invariant.rtg.constraints.live_status_boolean` | `RtgConstraints` | `registry` | Missing live normalizes to true and supplied live is Boolean. |
| `invariant.rtg.constraints.no_validation_execution` | `RtgConstraints` | `registry` | The store never executes constraints or validates graph objects. |
| `invariant.rtg.constraints.cardinality_rules_live_here` | `RtgConstraints` | `registry` | Query-binding cardinality rule definitions are owned here rather than in schema definitions. |
| `invariant.rtg.constraints.no_severity_policy_v1` | `RtgConstraints` | `registry` | V1 definitions contain no violation severity or blocking policy. |
| `invariant.rtg.constraints.pattern_compatibility` | `RtgConstraints` | `registry` | Query-pattern and cardinality payloads use the canonical RtgQuerySpec and name valid bindings structurally; evaluation belongs to validation/query. |
| `invariant.rtg.constraints.indexes_match_records` | `RtgConstraints` | `registry` | Derived kind, target, and live indexes exactly match canonical records. |
| `contract.rtg.constraints.export_constraint_snapshot.failures` | `ExportConstraintSnapshot` | `registry.exportSnapshot` | Export is state-neutral and has no declared domain failure. |
| `contract.rtg.constraints.put_constraint.failures` | `PutConstraint` | `registry.putConstraint` | Rejected writes leave canonical records and indexes unchanged. |
| `contract.rtg.constraints.get_constraint.failures` | `GetConstraint` | `registry.getConstraint` | Read failure has no effect. |
| `contract.rtg.constraints.list_constraints.failures` | `ListConstraints` | `registry.listConstraints` | Read failure has no effect. |
| `contract.rtg.constraints.list_constraints_by_target.failures` | `ListConstraintsByTarget` | `registry.listConstraintsByTarget` | Read failure has no effect and never inspects schema or graph state. |
| `contract.rtg.constraints.delete_constraint.failures` | `DeleteConstraint` | `registry.deleteConstraint` | Rejected delete has no effect. |
| `contract.rtg.constraints.create_empty_rtg_constraints.failures` | `CreateEmptyRtgConstraints` | `createEmptyRtgConstraintsSubject` | Construction has no declared domain failure. |
| `contract.rtg.constraints.import_rtg_constraint_snapshot.failures` | `ImportRtgConstraintSnapshot` | `importRtgConstraintSnapshotSubject` | Failure returns no partially imported registry. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgConstraintPayload` | `attribute` | — | One query-pattern or cardinality payload selected by constraint kind. |
| `RtgConstraintQueryPatternPayload` | `attribute` | `querySpec: RtgQuerySpec`, `expectation: RtgConstraintExpectation` | Defined by its typed fields and action requirements. |
| `RtgConstraintCardinalityPayload` | `attribute` | `querySpec: RtgQuerySpec`, `countedBinding: String`, `minimum[0..1]: Integer`, `maximum[0..1]: Integer` | Bounds are non-negative and at least one is present. |
| `RtgConstraintDefinition` | `item` | `uuid[0..1]: Uuid`, `kind: RtgConstraintKind`, `targetTypeKeys[0..*]: String`, `displayName: String`, `description: String`, `payload: RtgConstraintPayload`, `system: JsonObject` | UUID may be absent on write only. Stored definitions have concrete UUID and Boolean system.live, defaulting missing live to true. targetTypeKeys has native unique, unordered set semantics; duplicate inputs are invalid and realization encodings may use a canonical order. |
| `RtgConstraintSnapshot` | `attribute` | `constraints[0..*]: RtgConstraintDefinition` | Defined by its typed fields and action requirements. |
| `RtgConstraintDefinitionList` | `attribute` | `constraints[0..*]: RtgConstraintDefinition` | Defined by its typed fields and action requirements. |
| `RtgConstraintDeleteResult` | `attribute` | `deletedConstraint: RtgConstraintDefinition` | Defined by its typed fields and action requirements. |
| `RtgConstraintNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgConstraintSnapshotInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgConstraintUuidInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgConstraintUuidConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgConstraintKindInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgConstraintDefinitionInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgConstraintPayloadInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgConstraintSystemValueInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgConstraintTargetInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgConstraintKind` | `query_pattern`, `cardinality` |
| `RtgConstraintExpectation` | `must_match_at_least_one`, `must_match_none` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `PutConstraintContractVerification` | `PutConstraint` | `constraintWriteEffect`, `putConstraintFailureSemantics` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#PutConstraintContractVerification` |
| `DeleteConstraintContractVerification` | `DeleteConstraint` | `constraintDeleteEffect`, `deleteConstraintFailureSemantics` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#DeleteConstraintContractVerification` |
| `ExportConstraintSnapshotContractVerification` | `ExportConstraintSnapshot` | `exportConstraintSnapshotFailureSemantics` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#ExportConstraintSnapshotContractVerification` |
| `GetConstraintContractVerification` | `GetConstraint` | `getConstraintFailureSemantics` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#GetConstraintContractVerification` |
| `ListConstraintsContractVerification` | `ListConstraints` | `listConstraintsFailureSemantics` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#ListConstraintsContractVerification` |
| `ListConstraintsByTargetContractVerification` | `ListConstraintsByTarget` | `listConstraintsByTargetFailureSemantics` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#ListConstraintsByTargetContractVerification` |
| `CreateEmptyRtgConstraintsContractVerification` | `CreateEmptyRtgConstraints` | `createEmptyRtgConstraintsFailureSemantics` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#CreateEmptyRtgConstraintsContractVerification` |
| `ImportRtgConstraintSnapshotContractVerification` | `ImportRtgConstraintSnapshot` | `importRtgConstraintSnapshotFailureSemantics` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#ImportRtgConstraintSnapshotContractVerification` |
| `RtgConstraintsBoundaryVerification` | `RtgConstraints` | `constraintReadEffect`, `snapshotEffect`, `intentionalBoundary`, `uuidUnique`, `displayNameNotIdentity`, `liveStatusBoolean`, `noValidationExecution`, `cardinalityRulesLiveHere`, `noSeverityPolicyV1`, `patternCompatibility`, `indexesMatchRecords` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py#RtgConstraintsBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
