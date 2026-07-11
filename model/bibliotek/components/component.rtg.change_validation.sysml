library package BibliotekRtgChangeValidation {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;
    private import BibliotekRtgGraph::*;
    private import BibliotekRtgSchema::*;
    private import BibliotekRtgConstraints::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgDiagnostics::*;

    doc /* Deterministic, read-only validation of proposed RTG changes and supplied RTG state. */

    enum def RtgValidationTrack {
        enum schema_object;
        enum constraint_network;
        enum migration_cutover;
    }
    enum def RtgValidationSeverity { enum blocking; enum warning; enum informational; }
    enum def RtgValidationTrackSelection { enum 'all'; enum selected; }

    attribute def RtgResourceIdentifier {
        attribute uuid[0..1] : Uuid;
        attribute migrationId[0..1] : String;
        doc /* Exactly one representation identifies an existing or caller-assigned resource: UUID for graph/schema/constraint resources or text for migrations. */
    }
    attribute def RtgChangeReference {
        attribute resourceId[0..1] : RtgResourceIdentifier;
        attribute localRef[0..1] : String;
        doc /* Exactly one of resourceId and localRef identifies the target. localRef is unique within one batch and may be resolved by a controller before apply. */
    }
    attribute def RtgGraphAnchorWrite { attribute 'ref' : RtgChangeReference; attribute type : String; attribute displayName[0..1] : String; attribute system : JsonObject; }
    attribute def RtgGraphDataObjectWrite { attribute 'ref' : RtgChangeReference; attribute type : String; attribute properties : JsonObject; attribute system : JsonObject; attribute anchorRefs[1..*] : RtgChangeReference; }
    attribute def RtgGraphLinkWrite { attribute 'ref' : RtgChangeReference; attribute type : String; attribute sourceRef : RtgChangeReference; attribute targetRef : RtgChangeReference; attribute system : JsonObject; }
    attribute def RtgGraphAssociationChange { attribute anchorRef : RtgChangeReference; attribute dataRef : RtgChangeReference; }
    attribute def RtgGraphLiveStatusChange { attribute objectRef : RtgChangeReference; attribute live : Boolean; }
    attribute def RtgGraphChangeSet { attribute anchorWrites[0..*] : RtgGraphAnchorWrite; attribute dataObjectWrites[0..*] : RtgGraphDataObjectWrite; attribute linkWrites[0..*] : RtgGraphLinkWrite; attribute associateData[0..*] : RtgGraphAssociationChange; attribute dissociateData[0..*] : RtgGraphAssociationChange; attribute deleteAnchors[0..*] : RtgChangeReference; attribute deleteDataObjects[0..*] : RtgChangeReference; attribute deleteLinks[0..*] : RtgChangeReference; attribute setLive[0..*] : RtgGraphLiveStatusChange; }
    attribute def RtgSchemaDefinitionWrite { attribute 'ref' : RtgChangeReference; item definition : RtgSchemaDefinition; }
    attribute def RtgLiveStatusChange { attribute targetRef : RtgChangeReference; attribute live : Boolean; }
    attribute def RtgSchemaChangeSet { attribute definitionWrites[0..*] : RtgSchemaDefinitionWrite; attribute deleteDefinitions[0..*] : RtgChangeReference; attribute setLive[0..*] : RtgLiveStatusChange; }
    attribute def RtgConstraintDefinitionWrite { attribute 'ref' : RtgChangeReference; item 'constraint' : RtgConstraintDefinition; }
    attribute def RtgConstraintChangeSet { attribute constraintWrites[0..*] : RtgConstraintDefinitionWrite; attribute deleteConstraints[0..*] : RtgChangeReference; attribute setLive[0..*] : RtgLiveStatusChange; }
    attribute def RtgMigrationRecordWrite { attribute 'ref' : RtgChangeReference; item migration : RtgMigrationRecord; }
    attribute def RtgMigrationStatusChange { attribute migrationRef : RtgChangeReference; attribute status : RtgMigrationStatus; attribute statusMetadata : JsonObject; }
    attribute def RtgMigrationEvidenceAddition { attribute migrationRef : RtgChangeReference; attribute evidence : RtgMigrationEvidence; }
    attribute def RtgMigrationChangeSet { attribute migrationWrites[0..*] : RtgMigrationRecordWrite; attribute deleteMigrations[0..*] : RtgChangeReference; attribute statusChanges[0..*] : RtgMigrationStatusChange; attribute evidenceAdditions[0..*] : RtgMigrationEvidenceAddition; }
    attribute def RtgChangeBatch {
        attribute graphChanges[0..1] : RtgGraphChangeSet;
        attribute schemaChanges[0..1] : RtgSchemaChangeSet;
        attribute constraintChanges[0..1] : RtgConstraintChangeSet;
        attribute migrationChanges[0..1] : RtgMigrationChangeSet;
        doc /* An absent section is an empty change set. Categories remain explicit and use their component-owned public write values. */
    }
    attribute def RtgValidationOptions {
        attribute selection : RtgValidationTrackSelection = RtgValidationTrackSelection::'all';
        attribute tracks[0..*] : RtgValidationTrack;
        attribute findingLimit[0..1] : Integer;
        doc /* all executes every track; selected requires at least one unique track. findingLimit, when present, is positive and limits returned findings only. */
    }
    attribute def RtgValidationFinding { attribute track : RtgValidationTrack; attribute severity : RtgValidationSeverity; attribute code : String; attribute 'message' : String; attribute suggestion[0..1] : String; attribute affectedReferences[0..*] : String; attribute diagnostic : JsonObject; }
    attribute def RtgValidationReport { attribute accepted : Boolean; attribute findings[0..*] : RtgValidationFinding; attribute evidence : JsonObject; }
    attribute def RtgValidationInputInvalid { attribute 'message' : String; attribute diagnostic : JsonObject; }

    action def ValidateRtgChangeBatch {
        in graph : RtgGraphReadView;
        in schema : RtgSchema;
        in constraints : RtgConstraints;
        in migration[0..1] : RtgMigration;
        in query : RtgQueryEngine;
        in changeBatch : RtgChangeBatch;
        in validationOptions[0..1] : RtgValidationOptions;
        out report : RtgValidationReport;
        doc /* Project and validate only the tracks selected by options; absent options select all tracks. */
        @FailureContract { errorIds = ("RtgValidationInputInvalid"); }
    }
    action def ValidateRtgGraphState {
        in graph : RtgGraphReadView;
        in schema : RtgSchema;
        in constraints : RtgConstraints;
        in migration[0..1] : RtgMigration;
        in query : RtgQueryEngine;
        in migrationIds[0..*] : String;
        in validationOptions[0..1] : RtgValidationOptions;
        out report : RtgValidationReport;
        doc /* Validate the supplied current state, optionally limiting migration/cutover checks to the named migrations, without mutation. */
        @FailureContract { errorIds = ("RtgValidationInputInvalid"); }
    }

    part def <'component.rtg.change_validation'> RtgChangeValidator {
        doc /* Validate proposed RTG changes through independently selected tracks without owning or mutating RTG state. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }

        perform action validateBatch[0..*] : ValidateRtgChangeBatch {
            doc /* Select tracks before projection, execute only selected tracks, and report without mutation. */
            action selectTracks { doc /* Resolve absent options to all tracks; otherwise retain exactly the selected tracks. */ }
            action projectSelectedSections { doc /* Read and project only sections and capabilities required by selected tracks. */ }
            action executeSelectedTracks { doc /* Evaluate each selected rule catalog against its coherent projection. */ }
            action assembleReport { doc /* Deterministically order, deduplicate, limit, and summarize all produced findings. */ }
            first selectTracks then projectSelectedSections;
            first projectSelectedSections then executeSelectedTracks;
            first executeSelectedTracks then assembleReport;
        }
        perform action validateGraphState[0..*] : ValidateRtgGraphState { doc /* validate supplied or migration-selected state without mutation. */ }
    }


    requirement <'contract.rtg.change_validation.references'> referenceSemantics {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Each change reference has exactly one existing/caller identity or one batch-local identity. Local references resolve consistently across the selected projection; unresolved, duplicate, or kind-incompatible references are reported without mutation. */
        }
    }

    requirement <'contract.rtg.change_validation.projection'> projectionSemantics {
        subject operation : ValidateRtgChangeBatch;
        require constraint {
            doc /* Resolve batch-local references and construct separate proposed graph, schema, constraint, and migration views from public component semantics. Projection never mutates supplied sources. */
        }
    }

    requirement <'contract.rtg.change_validation.track_isolation'> trackIsolation {
        subject operation : ValidateRtgChangeBatch;
        require constraint {
            doc /* Select tracks before track-specific reference validation and projection. Each track reads and projects only its required sections and dependencies; malformed unselected sections cannot affect the report. */
        }
    }

    requirement <'contract.rtg.change_validation.rule_catalog'> validationRuleCatalog {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Stable blocking codes are schema_object.unknown_type, undeclared_property, property_kind_mismatch, missing_required_property, missing_required_associated_data, link_endpoint_type_invalid, reference_missing; constraint_network.pattern_unsatisfied, cardinality_out_of_bounds, constraint_target_unknown, constraint_payload_unevaluable; and migration_cutover.reference_missing, wrong_live_state, invalid_status_transition, post_state_invalid. migration_cutover.replacement_type_mismatch is warning. Each code retains this track and severity. */
        }
    }

    requirement <'contract.rtg.change_validation.rules'> validationRules {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Schema/object checks public schema compatibility and references; constraint/network evaluates compatible query patterns, cardinalities, targets, and payloads through query; migration/cutover checks membership, replacements, lifecycle, live state, and projected post-state. */
        }
    }

    requirement <'contract.rtg.change_validation.report'> reportSemantics {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Findings have stable track/code/reference identity, deterministic order, and deduplication. accepted is false when any produced finding is blocking. A positive limit returns blocking before warning/informational findings and evidence reports total, returned, and truncation without changing acceptance. */
        }
    }

    requirement <'invariant.rtg.change_validation.no_mutation'> noMutation {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Validation does not mutate any source component. */
        }
    }

    requirement <'invariant.rtg.change_validation.deterministic_reports'> deterministicReports {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Identical coherent views and requests produce identical ordered reports. */
        }
    }

    requirement <'invariant.rtg.change_validation.findings_are_comprehensive'> findingsComprehensive {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Acceptance considers every finding produced by executed tracks even when the returned list is limited. */
        }
    }

    requirement <'invariant.rtg.change_validation.source_of_truth_external'> sourceOfTruthExternal {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Source state remains owned by graph, schema, constraints, and migration components. */
        }
    }

    requirement <'invariant.rtg.change_validation.blocking_findings_control_acceptance'> blockingFindingsControlAcceptance {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* A blocking finding makes the report unaccepted. */
        }
    }

    requirement <'invariant.rtg.change_validation.findings_are_agent_actionable'> findingsAgentActionable {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Findings identify location, reason, and concise repair guidance where known. */
        }
    }

    requirement <'invariant.rtg.change_validation.tracks_are_extractable'> tracksExtractable {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Tracks remain isolated by source, dependencies, options, and findings. */
        }
    }

    requirement <'invariant.rtg.change_validation.batch_sections_explicit'> batchSectionsExplicit {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Proposed resource categories remain explicit in the change batch. */
        }
    }

    requirement <'invariant.rtg.change_validation.constraint_schema_compatibility'> constraintSchemaCompatibility {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Constraint targets and query paths are compatible with projected schema. */
        }
    }

    requirement <'invariant.rtg.change_validation.pattern_eval_delegated_to_query'> patternEvaluationDelegated {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Query-pattern evaluation uses the public query contract. */
        }
    }

    requirement <'invariant.rtg.change_validation.cascade_effects_from_graph_preview'> cascadeEffectsFromPreview {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Delete and dissociation projections use graph preview behavior. */
        }
    }

    requirement <'contract.rtg.change_validation.validate_rtg_change_batch.failures'> validateRtgChangeBatchFailureSemantics {
        subject operation : ValidateRtgChangeBatch;
        require constraint {
            doc /* Only structurally unusable inputs raise. Domain violations are findings, and every outcome has no effect on supplied state. */
        }
    }

    requirement <'contract.rtg.change_validation.validate_rtg_graph_state.failures'> validateRtgGraphStateFailureSemantics {
        subject operation : ValidateRtgGraphState;
        require constraint {
            doc /* Only structurally unusable inputs raise; the supplied component state and query engine remain unchanged. */
        }
    }

    part contractContext {
        part validator : RtgChangeValidator;
        satisfy referenceSemantics by validator;
        satisfy validationRuleCatalog by validator;
        satisfy validationRules by validator;
        satisfy reportSemantics by validator;
        satisfy noMutation by validator;
        satisfy deterministicReports by validator;
        satisfy findingsComprehensive by validator;
        satisfy sourceOfTruthExternal by validator;
        satisfy blockingFindingsControlAcceptance by validator;
        satisfy findingsAgentActionable by validator;
        satisfy tracksExtractable by validator;
        satisfy batchSectionsExplicit by validator;
        satisfy constraintSchemaCompatibility by validator;
        satisfy patternEvaluationDelegated by validator;
        satisfy cascadeEffectsFromPreview by validator;
        satisfy projectionSemantics by validator.validateBatch;
        satisfy trackIsolation by validator.validateBatch;

        satisfy validateRtgChangeBatchFailureSemantics by validator.validateBatch;
        satisfy validateRtgGraphStateFailureSemantics by validator.validateGraphState;
    }

    verification def ValidateRtgChangeBatchContractVerification {
        subject operation : ValidateRtgChangeBatch;
        objective {
            verify projectionSemantics;
            verify trackIsolation;

            verify validateRtgChangeBatchFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/change_validation/tests/test_rtg_change_validation_contract.py#ValidateRtgChangeBatchContractVerification";
            implementationScope = "DeterministicRtgChangeValidator";
        }
    }
    verification def ValidateRtgGraphStateContractVerification {
        subject operation : ValidateRtgGraphState;
        objective { verify validateRtgGraphStateFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/change_validation/tests/test_rtg_change_validation_contract.py#ValidateRtgGraphStateContractVerification"; implementationScope = "DeterministicRtgChangeValidator"; }
    }



    verification def RtgChangeValidationBoundaryVerification {
        subject validator : RtgChangeValidator;
        objective { verify referenceSemantics; verify validationRuleCatalog; verify validationRules; verify reportSemantics; verify noMutation; verify deterministicReports; verify findingsComprehensive; verify sourceOfTruthExternal; verify blockingFindingsControlAcceptance; verify findingsAgentActionable; verify tracksExtractable; verify batchSectionsExplicit; verify constraintSchemaCompatibility; verify patternEvaluationDelegated; verify cascadeEffectsFromPreview; }
        @EvidenceBinding { evidenceId = "components/rtg/change_validation/tests/test_rtg_change_validation_contract.py#RtgChangeValidationBoundaryVerification"; implementationScope = "DeterministicRtgChangeValidator"; }
    }
}
