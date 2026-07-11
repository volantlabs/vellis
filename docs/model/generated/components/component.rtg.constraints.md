# component.rtg.constraints

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgConstraints`
- Lifecycle: `accepted`
- Purpose: Own declarative constraint records and derived kind/target/live indexes, while evaluation remains with validation/query consumers.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `exportSnapshot` | `ExportConstraintSnapshot` | out `snapshot: RtgConstraintSnapshot` | None | Export every full constraint record without evaluating it or inspecting other components. |
| `putConstraint` | `PutConstraint` | in `constraint: RtgConstraintDefinition`; out `stored: RtgConstraintDefinition` | `RtgConstraintUuidInvalid`, `RtgConstraintUuidConflict`, `RtgConstraintKindInvalid`, `RtgConstraintDefinitionInvalid`, `RtgConstraintSystemValueInvalid` | Generate or preserve identity, validate kind-specific structure and bounds, and atomically create or fully replace one record. A kind/payload mismatch is RtgConstraintDefinitionInvalid. |
| `getConstraint` | `GetConstraint` | in `constraintUuid: Uuid`; out `constraint: RtgConstraintDefinition` | `RtgConstraintNotFound` | Return one full constraint definition by UUID without executing it. |
| `listConstraints` | `ListConstraints` | in `kind: RtgConstraintKind[0..1]`; in `live: Boolean[0..1]`; out `result: RtgConstraintDefinitionList` | `RtgConstraintKindInvalid` | List definitions with optional kind/live filters in deterministic order. |
| `listConstraintsByTarget` | `ListConstraintsByTarget` | in `targetTypeKey: String`; in `live: Boolean[0..1]`; out `result: RtgConstraintDefinitionList` | `RtgConstraintTargetInvalid` | List definitions whose target metadata contains one type key, optionally filtered by live status. |
| `deleteConstraint` | `DeleteConstraint` | in `constraintUuid: Uuid`; out `result: RtgConstraintDeleteResult` | `RtgConstraintNotFound` | Delete exactly one definition without cascading into graph, schema, migration, or validation state. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgConstraints` | out `constraints: RtgConstraints` | None | Return an empty registry with empty derived indexes. |
| `ImportRtgConstraintSnapshot` | in `snapshot: RtgConstraintSnapshot`; out `constraints: RtgConstraints` | `RtgConstraintSnapshotInvalid`, `RtgConstraintUuidInvalid`, `RtgConstraintUuidConflict`, `RtgConstraintDefinitionInvalid`, `RtgConstraintSystemValueInvalid` | Validate all identities, records, payloads, bounds, and system values before rebuilding indexes and exposing the registry. |

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

| Action | State / collaborator | Modeled effect |
|---|---|---|
| `exportSnapshot` | `constraintRecords` | read all canonical records. |
| `putConstraint` | `constraintRecords` | atomically create/replace one record and rebuild affected indexes. |
| `getConstraint` | `constraintRecords` | read one canonical record. |
| `listConstraints` | `derivedIndexes` | read kind/live indexes. |
| `listConstraintsByTarget` | `derivedIndexes` | read target/kind/live indexes. |
| `deleteConstraint` | `constraintRecords` | remove one record and affected indexes. |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.rtg.constraints.write_effect` | Missing UUID generates identity; supplied identity is preserved. Kind selects a compatible typed payload, descriptions remain human-readable, missing live becomes true, and writes do not execute rules. |
| `contract.rtg.constraints.read_effect` | Reads are deterministic, honor explicit filters, derive only from canonical records/indexes, and never inspect or mutate graph/schema state. |
| `contract.rtg.constraints.delete_effect` | Delete removes exactly one definition and index entries with no cross-component cascade. |
| `contract.rtg.constraints.snapshot_effect` | Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. |
| `invariant.rtg.constraints.uuid_unique` | Constraint UUIDs are unique. |
| `invariant.rtg.constraints.display_name_not_identity` | Display name is non-unique navigation text, not identity. |
| `invariant.rtg.constraints.live_status_boolean` | Missing live normalizes to true and supplied live is Boolean. |
| `invariant.rtg.constraints.no_validation_execution` | The store never executes constraints or validates graph objects. |
| `invariant.rtg.constraints.cardinality_rules_live_here` | Query-binding cardinality rule definitions are owned here rather than in schema definitions. |
| `invariant.rtg.constraints.no_severity_policy_v1` | V1 definitions contain no violation severity or blocking policy. |
| `invariant.rtg.constraints.pattern_compatibility` | Query-pattern and cardinality payloads use the canonical RtgQuerySpec and name valid bindings structurally; evaluation belongs to validation/query. |
| `invariant.rtg.constraints.indexes_match_records` | Derived kind, target, and live indexes exactly match canonical records. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgConstraintPayload` | `attribute` | — | One query-pattern or cardinality payload selected by constraint kind. |
| `RtgConstraintQueryPatternPayload` | `attribute` | `querySpec: RtgQuerySpec`, `expectation: RtgConstraintExpectation` | Defined by its typed fields and action requirements. |
| `RtgConstraintCardinalityPayload` | `attribute` | `querySpec: RtgQuerySpec`, `countedBinding: String`, `minimum[0..1]: Integer`, `maximum[0..1]: Integer` | Bounds are non-negative and at least one is present. |
| `RtgConstraintDefinition` | `item` | `uuid[0..1]: Uuid`, `kind: RtgConstraintKind`, `targetTypeKeys[0..*]: String`, `displayName: String`, `description: String`, `payload: RtgConstraintPayload`, `system: JsonObject` | UUID may be absent on write only. Stored definitions have concrete UUID and Boolean system.live, defaulting missing live to true. |
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

| Enumeration | Model and external values |
|---|---|
| `RtgConstraintKind` | `queryPattern` → `query_pattern`, `cardinality` |
| `RtgConstraintExpectation` | `mustMatchAtLeastOne` → `must_match_at_least_one`, `mustMatchNone` → `must_match_none` |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `RtgConstraintsBoundaryVerification` | `constraintWriteEffect`, `constraintReadEffect`, `constraintDeleteEffect`, `snapshotEffect`, `uuidUnique`, `displayNameNotIdentity`, `liveStatusBoolean`, `noValidationExecution`, `cardinalityRulesLiveHere`, `noSeverityPolicyV1`, `patternCompatibility`, `indexesMatchRecords` | `components/rtg/constraints/tests/test_rtg_constraints_contract.py` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
