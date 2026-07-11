package PythonImplementationDrift {
    private import ScalarValues::*;
    private import BibliotekRtgConstraints::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekRtgController::*;
    private import VellisLocalPythonRealization::*;

    doc /* Non-normative realization discrepancies. Logical SysML contracts remain authoritative. */

    metadata def ImplementationDrift {
        :>> annotatedElement : SysML::Dependency;
        attribute implementationSymbol : String;
        attribute observed : String;
        attribute expected : String;
        attribute 'verification' : String;
    }

    dependency <'drift.rtg.constraints.target_list_surface'> constraintsTargetListSurface
        from BibliotekRtgConstraints::constraintReadEffect
        to VellisLocalPythonRealization::InMemoryRtgConstraints {
        @ImplementationDrift {
            implementationSymbol = "components.rtg.constraints.protocol.RtgConstraints.list_constraints_by_target";
            observed = "The Python protocol adds an optional kind filter not present in the logical action.";
            expected = "The action accepts target type key and optional live only; kind filtering remains available through list constraints.";
            'verification' = "Align the boundary signature or approve a language-neutral contract addition.";
        }
    }

    dependency <'drift.rtg.constraints.payload_failure_name'> constraintsPayloadFailureName
        from BibliotekRtgConstraints::constraintWriteEffect
        to VellisLocalPythonRealization::InMemoryRtgConstraints {
        @ImplementationDrift {
            implementationSymbol = "components.rtg.constraints.implementation.InMemoryRtgConstraints.put_constraint";
            observed = "Malformed kind-specific payloads raise RtgConstraintPayloadInvalid.";
            expected = "Kind and payload shape mismatch reports RtgConstraintDefinitionInvalid.";
            'verification' = "Align the concrete failure or approve a distinct language-neutral failure.";
        }
    }

    dependency <'drift.rtg.query.json_kind_equality'> queryJsonKindEquality
        from BibliotekRtgQuery::predicateSemantics
        to VellisLocalPythonRealization::SimpleRtgQueryEngine {
        @ImplementationDrift {
            implementationSymbol = "components.rtg.query.implementation._predicate_matches";
            observed = "Python equality and membership treat Boolean true as equal to Number 1.";
            expected = "Equality and membership preserve JSON kinds; Boolean and number are never equal.";
            'verification' = "Add equals and contains boundary cases for true versus 1.";
        }
    }

    dependency <'drift.rtg.query.regex_dialect'> queryRegexDialect
        from BibliotekRtgQuery::predicateSemantics
        to VellisLocalPythonRealization::SimpleRtgQueryEngine {
        @ImplementationDrift {
            implementationSymbol = "components.rtg.query.implementation._regex_matches";
            observed = "Python re plus a token blacklist accepts named and numeric backreferences.";
            expected = "Accept only the deterministic RE2-style subset and reject backreferences and lookaround.";
            'verification' = "Add rejection cases for named and numeric backreferences and lookaround.";
        }
    }

    dependency <'drift.rtg.change_validation.track_isolation'> validationTrackIsolation
        from BibliotekRtgChangeValidation::trackIsolation
        to VellisLocalPythonRealization::DeterministicRtgChangeValidator {
        @ImplementationDrift {
            implementationSymbol = "components.rtg.change_validation.implementation.DeterministicRtgChangeValidator.validate_batch";
            observed = "Reference validation and projection inspect all batch sections before track isolation.";
            expected = "Unselected sections are not validated or projected and cannot affect the report.";
            'verification' = "Add malformed-unselected-section cases for each track selection.";
        }
    }

    dependency <'drift.rtg.migration.replacement_status'> migrationReplacementStatus
        from BibliotekRtgMigration::putMigrationEffect
        to VellisLocalPythonRealization::InMemoryRtgMigration {
        @ImplementationDrift {
            implementationSymbol = "components.rtg.migration.implementation.InMemoryRtgMigration.put_migration";
            observed = "Replacing an existing migration may assign any valid status.";
            expected = "Replacement preserves status or follows MigrationStatusTransitionAllowed.";
            'verification' = "Add replacement cases for allowed and skipped transitions.";
        }
    }

    dependency <'drift.rtg.migration.delete_failure_name'> migrationDeleteFailureName
        from BibliotekRtgMigration::RtgMigrationDeleteInvalid
        to VellisLocalPythonRealization::InMemoryRtgMigration {
        @ImplementationDrift {
            implementationSymbol = "components.rtg.migration.protocol.RtgMigrationDeleteRejected";
            observed = "The Python protocol names the rejected lifecycle outcome RtgMigrationDeleteRejected.";
            expected = "The language-neutral contract names the outcome RtgMigrationDeleteInvalid.";
            'verification' = "Align the Python name or approve a logical contract rename.";
        }
    }

    dependency <'drift.rtg.controller.system_state_fields'> controllerSystemStateFields
        from BibliotekRtgController::RtgControllerSystemState
        to VellisLocalPythonRealization::InProcessRtgController {
        @ImplementationDrift {
            implementationSymbol = "components.rtg.controller.protocol.RtgControllerSystemState";
            observed = "Python uses live_schema_summary and persisted_snapshots and adds last_transaction_timestamp.";
            expected = "The contract uses live_schema_counts and persisted_snapshot_paths without an extra timestamp.";
            'verification' = "Align the boundary value or approve a contract clarification.";
        }
    }
}
