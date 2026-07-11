library package BibliotekRtgConstraints {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekRtgQuery::*;
    private import ScalarValues::*;

    enum def RtgConstraintKind {
        enum <'query_pattern'> queryPattern;
        enum cardinality;
    }
    enum def RtgConstraintExpectation {
        enum <'must_match_at_least_one'> mustMatchAtLeastOne;
        enum <'must_match_none'> mustMatchNone;
    }

    attribute def RtgConstraintPayload { doc /* One query-pattern or cardinality payload selected by constraint kind. */ }
    attribute def RtgConstraintQueryPatternPayload :> RtgConstraintPayload {
        attribute querySpec : RtgQuerySpec;
        attribute expectation : RtgConstraintExpectation;
    }
    attribute def RtgConstraintCardinalityPayload :> RtgConstraintPayload {
        attribute querySpec : RtgQuerySpec;
        attribute countedBinding : String;
        attribute minimum[0..1] : Integer;
        attribute maximum[0..1] : Integer;
        doc /* Bounds are non-negative and at least one is present. */
    }
    item def RtgConstraintDefinition {
        attribute uuid[0..1] : Uuid;
        attribute kind : RtgConstraintKind;
        attribute targetTypeKeys[0..*] : String;
        attribute displayName : String;
        attribute description : String;
        attribute payload : RtgConstraintPayload;
        attribute system : JsonObject;
        doc /* UUID may be absent on write only. Stored definitions have concrete UUID and Boolean system.live, defaulting missing live to true. */
    }
    attribute def RtgConstraintSnapshot { attribute constraints[0..*] : RtgConstraintDefinition; }
    attribute def RtgConstraintDefinitionList { attribute constraints[0..*] : RtgConstraintDefinition; }
    attribute def RtgConstraintDeleteResult { attribute deletedConstraint : RtgConstraintDefinition; }

    attribute def RtgConstraintNotFound { attribute message : String; }
    attribute def RtgConstraintSnapshotInvalid { attribute message : String; }
    attribute def RtgConstraintUuidInvalid { attribute message : String; }
    attribute def RtgConstraintUuidConflict { attribute message : String; }
    attribute def RtgConstraintKindInvalid { attribute message : String; }
    attribute def RtgConstraintDefinitionInvalid { attribute message : String; }
    attribute def RtgConstraintPayloadInvalid { attribute message : String; }
    attribute def RtgConstraintSystemValueInvalid { attribute message : String; }
    attribute def RtgConstraintTargetInvalid { attribute message : String; }

    action def ExportConstraintSnapshot { out snapshot : RtgConstraintSnapshot; doc /* Export every full constraint record without evaluating it or inspecting other components. */ @FailureContract { errorIds = (); obligation = "Export is state-neutral and has no declared domain failure."; } }
    action def PutConstraint { in constraint : RtgConstraintDefinition; out stored : RtgConstraintDefinition; doc /* Generate or preserve identity, validate kind-specific structure and bounds, and atomically create or fully replace one record. A kind/payload mismatch is RtgConstraintDefinitionInvalid. */ @FailureContract { errorIds = ("RtgConstraintUuidInvalid", "RtgConstraintUuidConflict", "RtgConstraintKindInvalid", "RtgConstraintDefinitionInvalid", "RtgConstraintSystemValueInvalid"); obligation = "Rejected writes leave canonical records and indexes unchanged."; } }
    action def GetConstraint { in constraintUuid : Uuid; out constraint : RtgConstraintDefinition; doc /* Return one full constraint definition by UUID without executing it. */ @FailureContract { errorIds = ("RtgConstraintNotFound"); obligation = "Read failure has no effect."; } }
    action def ListConstraints { in kind[0..1] : RtgConstraintKind; in live[0..1] : Boolean; out result : RtgConstraintDefinitionList; doc /* List definitions with optional kind/live filters in deterministic order. */ @FailureContract { errorIds = ("RtgConstraintKindInvalid"); obligation = "Read failure has no effect."; } }
    action def ListConstraintsByTarget { in targetTypeKey : String; in live[0..1] : Boolean; out result : RtgConstraintDefinitionList; doc /* List definitions whose target metadata contains one type key, optionally filtered by live status. */ @FailureContract { errorIds = ("RtgConstraintTargetInvalid"); obligation = "Read failure has no effect and never inspects schema or graph state."; } }
    action def DeleteConstraint { in constraintUuid : Uuid; out result : RtgConstraintDeleteResult; doc /* Delete exactly one definition without cascading into graph, schema, migration, or validation state. */ @FailureContract { errorIds = ("RtgConstraintNotFound"); obligation = "Rejected delete has no effect."; } }

    part def <'component.rtg.constraints'> RtgConstraints {
        doc /* Own declarative constraint records and derived kind/target/live indexes, while evaluation remains with validation/query consumers. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        item constraintRecords[0..*] : RtgConstraintDefinition { doc /* Canonical component-owned constraint-definition occurrences. */ }
        derived attribute derivedIndexes : JsonObject { doc /* Ephemeral indexes derived from canonical constraint definitions. */ }
        perform action exportSnapshot[0..*] : ExportConstraintSnapshot; perform action putConstraint[0..*] : PutConstraint; perform action getConstraint[0..*] : GetConstraint;
        perform action listConstraints[0..*] : ListConstraints; perform action listConstraintsByTarget[0..*] : ListConstraintsByTarget; perform action deleteConstraint[0..*] : DeleteConstraint;
        dependency snapshotState from exportSnapshot to constraintRecords { doc /* read all canonical records. */ }
        dependency putState from putConstraint to constraintRecords { doc /* atomically create/replace one record and rebuild affected indexes. */ }
        dependency getState from getConstraint to constraintRecords { doc /* read one canonical record. */ }
        dependency listState from listConstraints to derivedIndexes { doc /* read kind/live indexes. */ }
        dependency targetState from listConstraintsByTarget to derivedIndexes { doc /* read target/kind/live indexes. */ }
        dependency deleteState from deleteConstraint to constraintRecords { doc /* remove one record and affected indexes. */ }
    }
    action def CreateEmptyRtgConstraints { out part constraints : RtgConstraints; doc /* Return an empty registry with empty derived indexes. */ @FailureContract { errorIds = (); obligation = "Construction has no declared domain failure."; } }
    action def ImportRtgConstraintSnapshot { in snapshot : RtgConstraintSnapshot; out part constraints : RtgConstraints; doc /* Validate all identities, records, payloads, bounds, and system values before rebuilding indexes and exposing the registry. */ @FailureContract { errorIds = ("RtgConstraintSnapshotInvalid", "RtgConstraintUuidInvalid", "RtgConstraintUuidConflict", "RtgConstraintDefinitionInvalid", "RtgConstraintSystemValueInvalid"); obligation = "Failure returns no partially imported registry."; } }

    requirement <'contract.rtg.constraints.write_effect'> constraintWriteEffect { subject operation : PutConstraint; doc /* Missing UUID generates identity; supplied identity is preserved. Kind selects a compatible typed payload, descriptions remain human-readable, missing live becomes true, and writes do not execute rules. */ }
    requirement <'contract.rtg.constraints.read_effect'> constraintReadEffect { subject constraints : RtgConstraints; doc /* Reads are deterministic, honor explicit filters, derive only from canonical records/indexes, and never inspect or mutate graph/schema state. */ }
    requirement <'contract.rtg.constraints.delete_effect'> constraintDeleteEffect { subject operation : DeleteConstraint; doc /* Delete removes exactly one definition and index entries with no cross-component cascade. */ }
    requirement <'contract.rtg.constraints.snapshot_effect'> snapshotEffect { subject constraints : RtgConstraints; doc /* Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. */ }
    requirement <'invariant.rtg.constraints.uuid_unique'> uuidUnique { subject constraints : RtgConstraints; doc /* Constraint UUIDs are unique. */ }
    requirement <'invariant.rtg.constraints.display_name_not_identity'> displayNameNotIdentity { subject constraints : RtgConstraints; doc /* Display name is non-unique navigation text, not identity. */ }
    requirement <'invariant.rtg.constraints.live_status_boolean'> liveStatusBoolean { subject constraints : RtgConstraints; doc /* Missing live normalizes to true and supplied live is Boolean. */ }
    requirement <'invariant.rtg.constraints.no_validation_execution'> noValidationExecution { subject constraints : RtgConstraints; doc /* The store never executes constraints or validates graph objects. */ }
    requirement <'invariant.rtg.constraints.cardinality_rules_live_here'> cardinalityRulesLiveHere { subject constraints : RtgConstraints; doc /* Query-binding cardinality rule definitions are owned here rather than in schema definitions. */ }
    requirement <'invariant.rtg.constraints.no_severity_policy_v1'> noSeverityPolicyV1 { subject constraints : RtgConstraints; doc /* V1 definitions contain no violation severity or blocking policy. */ }
    requirement <'invariant.rtg.constraints.pattern_compatibility'> patternCompatibility { subject constraints : RtgConstraints; doc /* Query-pattern and cardinality payloads use the canonical RtgQuerySpec and name valid bindings structurally; evaluation belongs to validation/query. */ }
    requirement <'invariant.rtg.constraints.indexes_match_records'> indexesMatchRecords { subject constraints : RtgConstraints; doc /* Derived kind, target, and live indexes exactly match canonical records. */ }

    verification def RtgConstraintsBoundaryVerification {
        subject constraints : RtgConstraints;
        objective { verify constraintWriteEffect; verify constraintReadEffect; verify constraintDeleteEffect; verify snapshotEffect; verify uuidUnique; verify displayNameNotIdentity; verify liveStatusBoolean; verify noValidationExecution; verify cardinalityRulesLiveHere; verify noSeverityPolicyV1; verify patternCompatibility; verify indexesMatchRecords; }
        @EvidenceBinding { verificationId = "verification.rtg.constraints.boundary"; evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py"; implementationScope = "InMemoryRtgConstraints"; }
    }
}
