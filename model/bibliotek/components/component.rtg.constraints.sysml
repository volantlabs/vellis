library package BibliotekRtgConstraints {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekRtgQuery::*;
    private import ScalarValues::*;

    enum def RtgConstraintKind {
        enum query_pattern;
        enum cardinality;
    }
    enum def RtgConstraintExpectation {
        enum must_match_at_least_one;
        enum must_match_none;
    }

    abstract attribute def RtgConstraintPayload { doc /* One query-pattern or cardinality payload selected by constraint kind. */ }
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
        doc /* UUID may be absent on write only. Stored definitions have concrete UUID and Boolean system.live, defaulting missing live to true. targetTypeKeys has native unique, unordered set semantics; duplicate inputs are invalid and realization encodings may use a canonical order. */
    }
    attribute def RtgConstraintSnapshot { item constraints[0..*] : RtgConstraintDefinition; }
    attribute def RtgConstraintDefinitionList { item constraints[0..*] : RtgConstraintDefinition; }
    attribute def RtgConstraintDeleteResult { item deletedConstraint : RtgConstraintDefinition; }

    attribute def RtgConstraintNotFound { attribute 'message' : String; }
    attribute def RtgConstraintSnapshotInvalid { attribute 'message' : String; }
    attribute def RtgConstraintUuidInvalid { attribute 'message' : String; }
    attribute def RtgConstraintUuidConflict { attribute 'message' : String; }
    attribute def RtgConstraintKindInvalid { attribute 'message' : String; }
    attribute def RtgConstraintDefinitionInvalid { attribute 'message' : String; }
    attribute def RtgConstraintPayloadInvalid { attribute 'message' : String; }
    attribute def RtgConstraintSystemValueInvalid { attribute 'message' : String; }
    attribute def RtgConstraintTargetInvalid { attribute 'message' : String; }

    action def ExportConstraintSnapshot { out 'snapshot' : RtgConstraintSnapshot; doc /* Export every full constraint record without evaluating it or inspecting other components. */ @FailureContract { errorIds = (); } }
    action def PutConstraint { in 'constraint' : RtgConstraintDefinition; out stored : RtgConstraintDefinition; doc /* Generate or preserve identity, validate kind-specific structure and bounds, and atomically create or fully replace one record. A kind/payload type mismatch is RtgConstraintDefinitionInvalid; malformed contents of the selected payload are RtgConstraintPayloadInvalid. */ @FailureContract { errorIds = ("RtgConstraintUuidInvalid", "RtgConstraintUuidConflict", "RtgConstraintKindInvalid", "RtgConstraintDefinitionInvalid", "RtgConstraintPayloadInvalid", "RtgConstraintSystemValueInvalid"); } }
    action def GetConstraint { in constraintUuid : Uuid; out 'constraint' : RtgConstraintDefinition; doc /* Return one full constraint definition by UUID without executing it. */ @FailureContract { errorIds = ("RtgConstraintNotFound"); } }
    action def ListConstraints { in kind[0..1] : RtgConstraintKind; in live[0..1] : Boolean; out result : RtgConstraintDefinitionList; doc /* List definitions with optional kind/live filters in deterministic order. */ @FailureContract { errorIds = ("RtgConstraintKindInvalid"); } }
    action def ListConstraintsByTarget { in targetTypeKey : String; in kind[0..1] : RtgConstraintKind; in live[0..1] : Boolean; out result : RtgConstraintDefinitionList; doc /* List definitions whose target metadata contains one type key, optionally filtered by constraint kind and live status. */ @FailureContract { errorIds = ("RtgConstraintTargetInvalid", "RtgConstraintKindInvalid"); } }
    action def DeleteConstraint { in constraintUuid : Uuid; out result : RtgConstraintDeleteResult; doc /* Delete exactly one definition without cascading into graph, schema, migration, or validation state. */ @FailureContract { errorIds = ("RtgConstraintNotFound"); } }

    part def <'component.rtg.constraints'> RtgConstraints {
        doc /* Own declarative constraint records and derived kind/target/live indexes, while evaluation remains with validation/query consumers. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        item constraintRecords[0..*] : RtgConstraintDefinition { doc /* Canonical component-owned constraint-definition occurrences. */ }
        derived attribute derivedIndexes : JsonObject { doc /* Ephemeral indexes derived from canonical constraint definitions. */ }
        perform action exportSnapshot[0..*] : ExportConstraintSnapshot; perform action putConstraint[0..*] : PutConstraint; perform action getConstraint[0..*] : GetConstraint;
        perform action listConstraints[0..*] : ListConstraints; perform action listConstraintsByTarget[0..*] : ListConstraintsByTarget; perform action deleteConstraint[0..*] : DeleteConstraint;
        dependency snapshotState from exportSnapshot to constraintRecords { @StateAccess { kind = StateAccessKind::read; } doc /* read all canonical records. */ }
        dependency putState from putConstraint to constraintRecords { @StateAccess { kind = StateAccessKind::write; } doc /* atomically create/replace one record and rebuild affected indexes. */ }
        dependency getState from getConstraint to constraintRecords { @StateAccess { kind = StateAccessKind::read; } doc /* read one canonical record. */ }
        dependency listState from listConstraints to derivedIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read kind/live indexes. */ }
        dependency targetState from listConstraintsByTarget to derivedIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read target/kind/live indexes. */ }
        dependency deleteState from deleteConstraint to constraintRecords { @StateAccess { kind = StateAccessKind::delete; } doc /* remove one record and affected indexes. */ }
    }
    action def CreateEmptyRtgConstraints { out part constraints : RtgConstraints; doc /* Return an empty registry with empty derived indexes. */ @FailureContract { errorIds = (); } }
    action def ImportRtgConstraintSnapshot { in 'snapshot' : RtgConstraintSnapshot; out part constraints : RtgConstraints; doc /* Validate all identities, records, payloads, bounds, and system values before rebuilding indexes and exposing the registry. */ @FailureContract { errorIds = ("RtgConstraintSnapshotInvalid", "RtgConstraintUuidInvalid", "RtgConstraintUuidConflict", "RtgConstraintKindInvalid", "RtgConstraintDefinitionInvalid", "RtgConstraintPayloadInvalid", "RtgConstraintSystemValueInvalid"); } }


    requirement <'contract.rtg.constraints.write_effect'> constraintWriteEffect {
        subject operation : PutConstraint;
        require constraint {
            doc /* Missing UUID generates identity; supplied identity is preserved. Kind selects a compatible typed payload, target keys are unique and unordered, descriptions remain human-readable, missing live becomes true, and writes do not execute rules. Duplicate target keys are rejected rather than silently repaired. */
        }
    }

    requirement <'contract.rtg.constraints.read_effect'> constraintReadEffect {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* Reads honor explicit filters, use ascending textual constraint UUID order, derive only from canonical records/indexes, and never inspect or mutate graph/schema state. */
        }
    }

    requirement <'contract.rtg.constraints.delete_effect'> constraintDeleteEffect {
        subject operation : DeleteConstraint;
        require constraint {
            doc /* Delete removes exactly one definition and index entries with no cross-component cascade. */
        }
    }

    requirement <'contract.rtg.constraints.snapshot_effect'> snapshotEffect {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. */
        }
    }

    requirement <'contract.rtg.constraints.intentional_boundary'> intentionalBoundary {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* This registry owns declarative definitions only. It does not execute constraints, inspect or mutate graph/schema/migration state, choose migration membership, own durable persistence or workflow, provide general graph query/inference, or attach v1 severity/blocking policy. UUID alone identifies a definition; names and target keys may be shared by multiple definitions. */
        }
    }

    requirement <'invariant.rtg.constraints.uuid_unique'> uuidUnique {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* Constraint UUIDs are unique. */
        }
    }

    requirement <'invariant.rtg.constraints.display_name_not_identity'> displayNameNotIdentity {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* Display name is non-unique navigation text, not identity. */
        }
    }

    requirement <'invariant.rtg.constraints.live_status_boolean'> liveStatusBoolean {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* Missing live normalizes to true and supplied live is Boolean. */
        }
    }

    requirement <'invariant.rtg.constraints.no_validation_execution'> noValidationExecution {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* The store never executes constraints or validates graph objects. */
        }
    }

    requirement <'invariant.rtg.constraints.cardinality_rules_live_here'> cardinalityRulesLiveHere {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* Query-binding cardinality rule definitions are owned here rather than in schema definitions. */
        }
    }

    requirement <'invariant.rtg.constraints.no_severity_policy_v1'> noSeverityPolicyV1 {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* V1 definitions contain no violation severity or blocking policy. */
        }
    }

    requirement <'invariant.rtg.constraints.pattern_compatibility'> patternCompatibility {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* Query-pattern and cardinality payloads use the canonical RtgQuerySpec and name valid bindings structurally; evaluation belongs to validation/query. */
        }
    }

    requirement <'invariant.rtg.constraints.indexes_match_records'> indexesMatchRecords {
        subject constraints : RtgConstraints;
        require constraint {
            doc /* Derived kind, target, and live indexes exactly match canonical records. */
        }
    }

    requirement <'contract.rtg.constraints.export_constraint_snapshot.failures'> exportConstraintSnapshotFailureSemantics {
        subject operation : ExportConstraintSnapshot;
        require constraint {
            doc /* Export is state-neutral and has no declared domain failure. */
        }
    }

    requirement <'contract.rtg.constraints.put_constraint.failures'> putConstraintFailureSemantics {
        subject operation : PutConstraint;
        require constraint {
            doc /* Rejected writes leave canonical records and indexes unchanged. */
        }
    }

    requirement <'contract.rtg.constraints.get_constraint.failures'> getConstraintFailureSemantics {
        subject operation : GetConstraint;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.constraints.list_constraints.failures'> listConstraintsFailureSemantics {
        subject operation : ListConstraints;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.constraints.list_constraints_by_target.failures'> listConstraintsByTargetFailureSemantics {
        subject operation : ListConstraintsByTarget;
        require constraint {
            doc /* Read failure has no effect and never inspects schema or graph state. */
        }
    }

    requirement <'contract.rtg.constraints.delete_constraint.failures'> deleteConstraintFailureSemantics {
        subject operation : DeleteConstraint;
        require constraint {
            doc /* Rejected delete has no effect. */
        }
    }

    requirement <'contract.rtg.constraints.create_empty_rtg_constraints.failures'> createEmptyRtgConstraintsFailureSemantics {
        subject operation : CreateEmptyRtgConstraints;
        require constraint {
            doc /* Construction has no declared domain failure. */
        }
    }

    requirement <'contract.rtg.constraints.import_rtg_constraint_snapshot.failures'> importRtgConstraintSnapshotFailureSemantics {
        subject operation : ImportRtgConstraintSnapshot;
        require constraint {
            doc /* Failure returns no partially imported registry. */
        }
    }

    part contractContext {
        part registry : RtgConstraints;
        satisfy constraintWriteEffect by registry.putConstraint;
        satisfy constraintReadEffect by registry;
        satisfy snapshotEffect by registry;
        satisfy intentionalBoundary by registry;
        satisfy uuidUnique by registry;
        satisfy displayNameNotIdentity by registry;
        satisfy liveStatusBoolean by registry;
        satisfy noValidationExecution by registry;
        satisfy cardinalityRulesLiveHere by registry;
        satisfy noSeverityPolicyV1 by registry;
        satisfy patternCompatibility by registry;
        satisfy indexesMatchRecords by registry;
        satisfy constraintDeleteEffect by registry.deleteConstraint;

        satisfy exportConstraintSnapshotFailureSemantics by registry.exportSnapshot;
        satisfy putConstraintFailureSemantics by registry.putConstraint;
        satisfy getConstraintFailureSemantics by registry.getConstraint;
        satisfy listConstraintsFailureSemantics by registry.listConstraints;
        satisfy listConstraintsByTargetFailureSemantics by registry.listConstraintsByTarget;
        satisfy deleteConstraintFailureSemantics by registry.deleteConstraint;
        action createEmptyRtgConstraintsSubject : CreateEmptyRtgConstraints;
        satisfy createEmptyRtgConstraintsFailureSemantics by createEmptyRtgConstraintsSubject;
        action importRtgConstraintSnapshotSubject : ImportRtgConstraintSnapshot;
        satisfy importRtgConstraintSnapshotFailureSemantics by importRtgConstraintSnapshotSubject;
    }

    verification def PutConstraintContractVerification {
        subject operation : PutConstraint;
        objective {
            verify constraintWriteEffect;

            verify putConstraintFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#PutConstraintContractVerification";
            implementationScope = "InMemoryRtgConstraints";
        }
    }

    verification def DeleteConstraintContractVerification {
        subject operation : DeleteConstraint;
        objective {
            verify constraintDeleteEffect;

            verify deleteConstraintFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#DeleteConstraintContractVerification";
            implementationScope = "InMemoryRtgConstraints";
        }
    }
    verification def ExportConstraintSnapshotContractVerification {
        subject operation : ExportConstraintSnapshot;
        objective { verify exportConstraintSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#ExportConstraintSnapshotContractVerification"; implementationScope = "InMemoryRtgConstraints"; }
    }

    verification def GetConstraintContractVerification {
        subject operation : GetConstraint;
        objective { verify getConstraintFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#GetConstraintContractVerification"; implementationScope = "InMemoryRtgConstraints"; }
    }

    verification def ListConstraintsContractVerification {
        subject operation : ListConstraints;
        objective { verify listConstraintsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#ListConstraintsContractVerification"; implementationScope = "InMemoryRtgConstraints"; }
    }

    verification def ListConstraintsByTargetContractVerification {
        subject operation : ListConstraintsByTarget;
        objective { verify listConstraintsByTargetFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#ListConstraintsByTargetContractVerification"; implementationScope = "InMemoryRtgConstraints"; }
    }

    verification def CreateEmptyRtgConstraintsContractVerification {
        subject operation : CreateEmptyRtgConstraints;
        objective { verify createEmptyRtgConstraintsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#CreateEmptyRtgConstraintsContractVerification"; implementationScope = "InMemoryRtgConstraints"; }
    }

    verification def ImportRtgConstraintSnapshotContractVerification {
        subject operation : ImportRtgConstraintSnapshot;
        objective { verify importRtgConstraintSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#ImportRtgConstraintSnapshotContractVerification"; implementationScope = "InMemoryRtgConstraints"; }
    }



    verification def RtgConstraintsBoundaryVerification {
        subject constraints : RtgConstraints;
        objective { verify constraintReadEffect; verify snapshotEffect; verify intentionalBoundary; verify uuidUnique; verify displayNameNotIdentity; verify liveStatusBoolean; verify noValidationExecution; verify cardinalityRulesLiveHere; verify noSeverityPolicyV1; verify patternCompatibility; verify indexesMatchRecords; }
        @EvidenceBinding { evidenceId = "components/rtg/constraints/tests/test_rtg_constraints_contract.py#RtgConstraintsBoundaryVerification"; implementationScope = "InMemoryRtgConstraints"; }
    }
}
