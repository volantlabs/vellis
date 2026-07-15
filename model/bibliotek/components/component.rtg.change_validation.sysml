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
    enum def RtgIdentityOverrideMode { enum force_create; }
    attribute def RtgIdentityOverride { attribute mode : RtgIdentityOverrideMode; attribute reason : String; attribute criterionKeys[0..*] : String; }
    attribute def RtgGraphAnchorWrite { attribute 'ref' : RtgChangeReference; attribute type : String; attribute displayName[0..1] : String; attribute system : JsonObject; attribute identityOverride[0..1] : RtgIdentityOverride; }
    attribute def RtgGraphDataObjectWrite { attribute 'ref' : RtgChangeReference; attribute type : String; attribute properties : JsonObject; attribute system : JsonObject; attribute anchorRefs[1..*] : RtgChangeReference; attribute identityOverride[0..1] : RtgIdentityOverride; }
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
        attribute selection : RtgValidationTrackSelection default = RtgValidationTrackSelection::'all';
        attribute tracks[0..*] : RtgValidationTrack;
        attribute findingLimit[0..1] : Integer;
        doc /* Canonical normalized options. all requires an empty tracks collection and executes every track; selected requires a non-empty unique tracks collection and executes exactly those tracks. findingLimit, when present, is positive and limits returned findings only. */
    }
    attribute def RtgValidationFinding { attribute track : RtgValidationTrack; attribute severity : RtgValidationSeverity; attribute code : String; attribute 'message' : String; attribute suggestion[0..1] : String; attribute affectedReferences[0..*] : String; attribute diagnostic[0..1] : RtgDiagnostic; }
    attribute def RtgValidationReport { attribute accepted : Boolean; attribute findings[0..*] : RtgValidationFinding; attribute evidence : JsonObject; }
    attribute def RtgValidationInputInvalid { attribute 'message' : String; }

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
            doc /* Each change reference has exactly one existing/caller identity or one batch-local identity. Local references resolve consistently across the selected projection; unresolved, duplicate, kind-incompatible, or otherwise unprojectable operations are reported as blocking findings without mutation rather than escaping as foreign component failures. */
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
            doc /* Select tracks before track-specific reference validation and projection. schema_object reads and projects graph and schema; constraint_network reads and projects graph, schema, and constraints and invokes query; migration_cutover may read and project all four stores. Malformed unselected sections and unavailable unselected dependencies cannot affect the report. */
        }
    }

    requirement <'contract.rtg.change_validation.rule_catalog'> validationRuleCatalog {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Stable blocking codes include schema_object.unknown_type, undeclared_property, property_kind_mismatch, missing_required_property, missing_required_associated_data, link_endpoint_type_invalid, reference_missing, kernel_system_field_write_rejected, event_update_rejected, link_kind_missing, link_kind_invalid, provenance_link_delete_rejected, and merge_candidate.identity_match; constraint_network.pattern_unsatisfied, cardinality_out_of_bounds, constraint_target_unknown, constraint_payload_unevaluable; and migration_cutover.reference_missing, wrong_live_state, invalid_status_transition, post_state_invalid, invalid_time_shape_retrofit. schema_object.delete_blast_radius_by_kind and merge_candidate.identity_force_create_override are informational; migration_cutover.replacement_type_mismatch is warning. Each code retains its declared track and severity. */
        }
    }

    requirement <'contract.rtg.change_validation.rules'> validationRules {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Schema/object checks public schema compatibility and references; constraint/network evaluates compatible query patterns, cardinalities, targets, and payloads through query; migration/cutover checks membership, replacements, lifecycle, live state, and projected post-state. */
        }
    }

    requirement <'contract.rtg.change_validation.kernel_meta_model'> kernelMetaModelValidation {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Schema/object validation rejects caller writes to created_at or updated_at, rejects updates to existing event-shaped data objects while permitting new event records, and reports a proposed insert matching live same-type identity criteria as a blocking merge candidate without mutation. An explicit force_create override requires a non-empty reason, optionally scopes named criteria, converts each corresponding identity match to informational evidence, and remains part of the resolved request. Staged link definitions require a recognized link kind. Direct provenance-link deletion outside migration is blocking, while anchor deletion reports the complete affected-link blast radius grouped by kind before apply. Migration projection applies only declared valid node time-shape retrofits. */
        }
    }

    requirement <'contract.rtg.change_validation.report'> reportSemantics {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Finding identity is the tuple (track, code, affected-reference sequence). Findings are de-duplicated by that identity before acceptance, evidence counts, limiting, and canonical ordering. Canonical order is severity (blocking, warning, informational), then track, code, and affected-reference sequence. accepted is false when any unique produced finding is blocking. A positive limit returns that canonical prefix and evidence reports total unique, returned, and truncation without changing acceptance. */
        }
    }

    requirement <'contract.rtg.change_validation.options'> validationOptionSemantics {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Absent options normalize to selection=all with no explicit tracks and no finding limit. selection=all is valid only with an empty tracks collection. selection=selected is valid only with one or more unique track literals. A present findingLimit is positive. Invalid combinations raise RtgValidationInputInvalid without reading or mutating supplied component state. */
        }
    }

    requirement <'contract.rtg.change_validation.intentional_boundary'> intentionalBoundary {
        subject validator : RtgChangeValidator;
        require constraint {
            doc /* Validation is stateless and report-only. It stores no graph, schema, constraint, or migration records; performs no mutation, publication, cutover, persistence, authorization, UI, or distributed coordination; and returns validation evidence rather than a general query result. */
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
        satisfy kernelMetaModelValidation by validator;
        satisfy reportSemantics by validator;
        satisfy validationOptionSemantics by validator;
        satisfy intentionalBoundary by validator;
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
        objective { verify referenceSemantics; verify validationRuleCatalog; verify validationRules; verify kernelMetaModelValidation; verify reportSemantics; verify validationOptionSemantics; verify intentionalBoundary; verify noMutation; verify deterministicReports; verify findingsComprehensive; verify sourceOfTruthExternal; verify blockingFindingsControlAcceptance; verify findingsAgentActionable; verify tracksExtractable; verify batchSectionsExplicit; verify constraintSchemaCompatibility; verify patternEvaluationDelegated; verify cascadeEffectsFromPreview; }
        @EvidenceBinding { evidenceId = "components/rtg/change_validation/tests/test_rtg_change_validation_contract.py#RtgChangeValidationBoundaryVerification"; implementationScope = "DeterministicRtgChangeValidator"; }
    }
}
