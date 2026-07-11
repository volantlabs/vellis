library package BibliotekRtgConstraints {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekRtgQuery::*;
    private import ScalarValues::*;

    enum def RtgConstraintKind {
        enum queryPattern { @ExternalName { name = "query_pattern"; } }
        enum cardinality;
    }
    enum def RtgConstraintExpectation {
        enum mustMatchAtLeastOne { @ExternalName { name = "must_match_at_least_one"; } }
        enum mustMatchNone { @ExternalName { name = "must_match_none"; } }
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

    part def RtgConstraints {
        doc /* Own declarative constraint records and derived kind/target/live indexes, while evaluation remains with validation/query consumers. */
        @SpecIdentity { id = "component.rtg.constraints"; lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        @DependencyPolicy { allowedComponentIds = ("component.rtg.query"); forbiddenComponentIds = ("component.rtg.graph", "component.rtg.schema", "component.rtg.migration", "component.rtg.controller"); }
        item constraintRecords[0..*] : RtgConstraintDefinition { @StateAuthority { authority = StateAuthorityKind::canonicalOwner; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        attribute derivedIndexes : JsonObject { @StateAuthority { authority = StateAuthorityKind::derived; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        perform action exportSnapshot[0..*] : ExportConstraintSnapshot; perform action putConstraint[0..*] : PutConstraint; perform action getConstraint[0..*] : GetConstraint;
        perform action listConstraints[0..*] : ListConstraints; perform action listConstraintsByTarget[0..*] : ListConstraintsByTarget; perform action deleteConstraint[0..*] : DeleteConstraint;
        dependency snapshotState from exportSnapshot to constraintRecords { @StateAccess { kind = StateAccessKind::read; effect = "read all canonical records"; } }
        dependency putState from putConstraint to constraintRecords { @StateAccess { kind = StateAccessKind::write; effect = "atomically create/replace one record and rebuild affected indexes"; } }
        dependency getState from getConstraint to constraintRecords { @StateAccess { kind = StateAccessKind::read; effect = "read one canonical record"; } }
        dependency listState from listConstraints to derivedIndexes { @StateAccess { kind = StateAccessKind::read; effect = "read kind/live indexes"; } }
        dependency targetState from listConstraintsByTarget to derivedIndexes { @StateAccess { kind = StateAccessKind::read; effect = "read target/kind/live indexes"; } }
        dependency deleteState from deleteConstraint to constraintRecords { @StateAccess { kind = StateAccessKind::delete; effect = "remove one record and affected indexes"; } }
    }
    action def CreateEmptyRtgConstraints { out part constraints : RtgConstraints; doc /* Return an empty registry with empty derived indexes. */ @FailureContract { errorIds = (); obligation = "Construction has no declared domain failure."; } }
    action def ImportRtgConstraintSnapshot { in snapshot : RtgConstraintSnapshot; out part constraints : RtgConstraints; doc /* Validate all identities, records, payloads, bounds, and system values before rebuilding indexes and exposing the registry. */ @FailureContract { errorIds = ("RtgConstraintSnapshotInvalid", "RtgConstraintUuidInvalid", "RtgConstraintUuidConflict", "RtgConstraintDefinitionInvalid", "RtgConstraintSystemValueInvalid"); obligation = "Failure returns no partially imported registry."; } }

    requirement constraintWriteEffect { subject operation : PutConstraint; doc /* Missing UUID generates identity; supplied identity is preserved. Kind selects a compatible typed payload, descriptions remain human-readable, missing live becomes true, and writes do not execute rules. */ @StableId { id = "contract.rtg.constraints.write_effect"; } }
    requirement constraintReadEffect { subject constraints : RtgConstraints; doc /* Reads are deterministic, honor explicit filters, derive only from canonical records/indexes, and never inspect or mutate graph/schema state. */ @StableId { id = "contract.rtg.constraints.read_effect"; } }
    requirement constraintDeleteEffect { subject operation : DeleteConstraint; doc /* Delete removes exactly one definition and index entries with no cross-component cascade. */ @StableId { id = "contract.rtg.constraints.delete_effect"; } }
    requirement snapshotEffect { subject constraints : RtgConstraints; doc /* Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. */ @StableId { id = "contract.rtg.constraints.snapshot_effect"; } }
    requirement uuidUnique { subject constraints : RtgConstraints; doc /* Constraint UUIDs are unique. */ @StableId { id = "invariant.rtg.constraints.uuid_unique"; } }
    requirement displayNameNotIdentity { subject constraints : RtgConstraints; doc /* Display name is non-unique navigation text, not identity. */ @StableId { id = "invariant.rtg.constraints.display_name_not_identity"; } }
    requirement liveStatusBoolean { subject constraints : RtgConstraints; doc /* Missing live normalizes to true and supplied live is Boolean. */ @StableId { id = "invariant.rtg.constraints.live_status_boolean"; } }
    requirement noValidationExecution { subject constraints : RtgConstraints; doc /* The store never executes constraints or validates graph objects. */ @StableId { id = "invariant.rtg.constraints.no_validation_execution"; } }
    requirement cardinalityRulesLiveHere { subject constraints : RtgConstraints; doc /* Query-binding cardinality rule definitions are owned here rather than in schema definitions. */ @StableId { id = "invariant.rtg.constraints.cardinality_rules_live_here"; } }
    requirement noSeverityPolicyV1 { subject constraints : RtgConstraints; doc /* V1 definitions contain no violation severity or blocking policy. */ @StableId { id = "invariant.rtg.constraints.no_severity_policy_v1"; } }
    requirement patternCompatibility { subject constraints : RtgConstraints; doc /* Query-pattern and cardinality payloads use the canonical RtgQuerySpec and name valid bindings structurally; evaluation belongs to validation/query. */ @StableId { id = "invariant.rtg.constraints.pattern_compatibility"; } }
    requirement indexesMatchRecords { subject constraints : RtgConstraints; doc /* Derived kind, target, and live indexes exactly match canonical records. */ @StableId { id = "invariant.rtg.constraints.indexes_match_records"; } }

    verification def RtgConstraintsBoundaryVerification {
        subject constraints : RtgConstraints;
        objective { verify constraintWriteEffect; verify constraintReadEffect; verify constraintDeleteEffect; verify snapshotEffect; verify uuidUnique; verify displayNameNotIdentity; verify liveStatusBoolean; verify noValidationExecution; verify cardinalityRulesLiveHere; verify noSeverityPolicyV1; verify patternCompatibility; verify indexesMatchRecords; }
        @EvidenceBinding { verificationId = "verification.rtg.constraints.boundary"; evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py"; implementationScope = "InMemoryRtgConstraints"; }
    }
}
