# component.rtg.change_validation

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgChangeValidator`
- Lifecycle: `accepted`
- Purpose: Validate proposed RTG changes through independently selected tracks without owning or mutating RTG state.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `validateBatch` | `ValidateRtgChangeBatch` | in `graph: RtgGraphReadView`; in `schema: RtgSchema`; in `constraints: RtgConstraints`; in `migration: RtgMigration[0..1]`; in `query: RtgQueryEngine`; in `changeBatch: RtgChangeBatch`; in `validationOptions: RtgValidationOptions[0..1]`; out `report: RtgValidationReport` | `RtgValidationInputInvalid` | Project and validate only the tracks selected by options; absent options select all tracks. |
| `validateGraphState` | `ValidateRtgGraphState` | in `graph: RtgGraphReadView`; in `schema: RtgSchema`; in `constraints: RtgConstraints`; in `migration: RtgMigration[0..1]`; in `query: RtgQueryEngine`; in `migrationIds: String[0..*]`; in `validationOptions: RtgValidationOptions[0..1]`; out `report: RtgValidationReport` | `RtgValidationInputInvalid` | Validate the supplied current state, optionally limiting migration/cutover checks to the named migrations, without mutation. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| — | — | — | No package-level construction action. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| — | — | — | This component owns no abstract state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `validateBatch` | — | `declared` | Select tracks before projection, execute only selected tracks, and report without mutation. |
| `validateGraphState` | — | `declared` | validate supplied or migration-selected state without mutation. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| `validateBatch` | `selectTracks: local`, `projectSelectedSections: local`, `executeSelectedTracks: local`, `assembleReport: local` | `first selectTracks then projectSelectedSections;`; `first projectSelectedSections then executeSelectedTracks;`; `first executeSelectedTracks then assembleReport;` |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.change_validation.references` | `RtgChangeValidator` | `validator` | Each change reference has exactly one existing/caller identity or one batch-local identity. Local references resolve consistently across the selected projection; unresolved, duplicate, or kind-incompatible references are reported without mutation. |
| `contract.rtg.change_validation.projection` | `ValidateRtgChangeBatch` | `validator.validateBatch` | Resolve batch-local references and construct separate proposed graph, schema, constraint, and migration views from public component semantics. Projection never mutates supplied sources. |
| `contract.rtg.change_validation.track_isolation` | `ValidateRtgChangeBatch` | `validator.validateBatch` | Select tracks before track-specific reference validation and projection. Each track reads and projects only its required sections and dependencies; malformed unselected sections cannot affect the report. |
| `contract.rtg.change_validation.rule_catalog` | `RtgChangeValidator` | `validator` | Stable blocking codes are schema_object.unknown_type, undeclared_property, property_kind_mismatch, missing_required_property, missing_required_associated_data, link_endpoint_type_invalid, reference_missing; constraint_network.pattern_unsatisfied, cardinality_out_of_bounds, constraint_target_unknown, constraint_payload_unevaluable; and migration_cutover.reference_missing, wrong_live_state, invalid_status_transition, post_state_invalid. migration_cutover.replacement_type_mismatch is warning. Each code retains this track and severity. |
| `contract.rtg.change_validation.rules` | `RtgChangeValidator` | `validator` | Schema/object checks public schema compatibility and references; constraint/network evaluates compatible query patterns, cardinalities, targets, and payloads through query; migration/cutover checks membership, replacements, lifecycle, live state, and projected post-state. |
| `contract.rtg.change_validation.report` | `RtgChangeValidator` | `validator` | Findings have stable track/code/reference identity, deterministic order, and deduplication. accepted is false when any produced finding is blocking. A positive limit returns blocking before warning/informational findings and evidence reports total, returned, and truncation without changing acceptance. |
| `invariant.rtg.change_validation.no_mutation` | `RtgChangeValidator` | `validator` | Validation does not mutate any source component. |
| `invariant.rtg.change_validation.deterministic_reports` | `RtgChangeValidator` | `validator` | Identical coherent views and requests produce identical ordered reports. |
| `invariant.rtg.change_validation.findings_are_comprehensive` | `RtgChangeValidator` | `validator` | Acceptance considers every finding produced by executed tracks even when the returned list is limited. |
| `invariant.rtg.change_validation.source_of_truth_external` | `RtgChangeValidator` | `validator` | Source state remains owned by graph, schema, constraints, and migration components. |
| `invariant.rtg.change_validation.blocking_findings_control_acceptance` | `RtgChangeValidator` | `validator` | A blocking finding makes the report unaccepted. |
| `invariant.rtg.change_validation.findings_are_agent_actionable` | `RtgChangeValidator` | `validator` | Findings identify location, reason, and concise repair guidance where known. |
| `invariant.rtg.change_validation.tracks_are_extractable` | `RtgChangeValidator` | `validator` | Tracks remain isolated by source, dependencies, options, and findings. |
| `invariant.rtg.change_validation.batch_sections_explicit` | `RtgChangeValidator` | `validator` | Proposed resource categories remain explicit in the change batch. |
| `invariant.rtg.change_validation.constraint_schema_compatibility` | `RtgChangeValidator` | `validator` | Constraint targets and query paths are compatible with projected schema. |
| `invariant.rtg.change_validation.pattern_eval_delegated_to_query` | `RtgChangeValidator` | `validator` | Query-pattern evaluation uses the public query contract. |
| `invariant.rtg.change_validation.cascade_effects_from_graph_preview` | `RtgChangeValidator` | `validator` | Delete and dissociation projections use graph preview behavior. |
| `contract.rtg.change_validation.validate_rtg_change_batch.failures` | `ValidateRtgChangeBatch` | `validator.validateBatch` | Only structurally unusable inputs raise. Domain violations are findings, and every outcome has no effect on supplied state. |
| `contract.rtg.change_validation.validate_rtg_graph_state.failures` | `ValidateRtgGraphState` | `validator.validateGraphState` | Only structurally unusable inputs raise; the supplied component state and query engine remain unchanged. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgResourceIdentifier` | `attribute` | `uuid[0..1]: Uuid`, `migrationId[0..1]: String` | Exactly one representation identifies an existing or caller-assigned resource: UUID for graph/schema/constraint resources or text for migrations. |
| `RtgChangeReference` | `attribute` | `resourceId[0..1]: RtgResourceIdentifier`, `localRef[0..1]: String` | Exactly one of resourceId and localRef identifies the target. localRef is unique within one batch and may be resolved by a controller before apply. |
| `RtgGraphAnchorWrite` | `attribute` | `ref: RtgChangeReference`, `type: String`, `displayName[0..1]: String`, `system: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgGraphDataObjectWrite` | `attribute` | `ref: RtgChangeReference`, `type: String`, `properties: JsonObject`, `system: JsonObject`, `anchorRefs[1..*]: RtgChangeReference` | Defined by its typed fields and action requirements. |
| `RtgGraphLinkWrite` | `attribute` | `ref: RtgChangeReference`, `type: String`, `sourceRef: RtgChangeReference`, `targetRef: RtgChangeReference`, `system: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgGraphAssociationChange` | `attribute` | `anchorRef: RtgChangeReference`, `dataRef: RtgChangeReference` | Defined by its typed fields and action requirements. |
| `RtgGraphLiveStatusChange` | `attribute` | `objectRef: RtgChangeReference`, `live: Boolean` | Defined by its typed fields and action requirements. |
| `RtgGraphChangeSet` | `attribute` | `anchorWrites[0..*]: RtgGraphAnchorWrite`, `dataObjectWrites[0..*]: RtgGraphDataObjectWrite`, `linkWrites[0..*]: RtgGraphLinkWrite`, `associateData[0..*]: RtgGraphAssociationChange`, `dissociateData[0..*]: RtgGraphAssociationChange`, `deleteAnchors[0..*]: RtgChangeReference`, `deleteDataObjects[0..*]: RtgChangeReference`, `deleteLinks[0..*]: RtgChangeReference`, `setLive[0..*]: RtgGraphLiveStatusChange` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionWrite` | `attribute` | `ref: RtgChangeReference`, `definition: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgLiveStatusChange` | `attribute` | `targetRef: RtgChangeReference`, `live: Boolean` | Defined by its typed fields and action requirements. |
| `RtgSchemaChangeSet` | `attribute` | `definitionWrites[0..*]: RtgSchemaDefinitionWrite`, `deleteDefinitions[0..*]: RtgChangeReference`, `setLive[0..*]: RtgLiveStatusChange` | Defined by its typed fields and action requirements. |
| `RtgConstraintDefinitionWrite` | `attribute` | `ref: RtgChangeReference`, `constraint: RtgConstraintDefinition` | Defined by its typed fields and action requirements. |
| `RtgConstraintChangeSet` | `attribute` | `constraintWrites[0..*]: RtgConstraintDefinitionWrite`, `deleteConstraints[0..*]: RtgChangeReference`, `setLive[0..*]: RtgLiveStatusChange` | Defined by its typed fields and action requirements. |
| `RtgMigrationRecordWrite` | `attribute` | `ref: RtgChangeReference`, `migration: RtgMigrationRecord` | Defined by its typed fields and action requirements. |
| `RtgMigrationStatusChange` | `attribute` | `migrationRef: RtgChangeReference`, `status: RtgMigrationStatus`, `statusMetadata: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgMigrationEvidenceAddition` | `attribute` | `migrationRef: RtgChangeReference`, `evidence: RtgMigrationEvidence` | Defined by its typed fields and action requirements. |
| `RtgMigrationChangeSet` | `attribute` | `migrationWrites[0..*]: RtgMigrationRecordWrite`, `deleteMigrations[0..*]: RtgChangeReference`, `statusChanges[0..*]: RtgMigrationStatusChange`, `evidenceAdditions[0..*]: RtgMigrationEvidenceAddition` | Defined by its typed fields and action requirements. |
| `RtgChangeBatch` | `attribute` | `graphChanges[0..1]: RtgGraphChangeSet`, `schemaChanges[0..1]: RtgSchemaChangeSet`, `constraintChanges[0..1]: RtgConstraintChangeSet`, `migrationChanges[0..1]: RtgMigrationChangeSet` | An absent section is an empty change set. Categories remain explicit and use their component-owned public write values. |
| `RtgValidationOptions` | `attribute` | `selection: RtgValidationTrackSelection` = `RtgValidationTrackSelection::'all'`, `tracks[0..*]: RtgValidationTrack`, `findingLimit[0..1]: Integer` | all executes every track; selected requires at least one unique track. findingLimit, when present, is positive and limits returned findings only. |
| `RtgValidationFinding` | `attribute` | `track: RtgValidationTrack`, `severity: RtgValidationSeverity`, `code: String`, `message: String`, `suggestion[0..1]: String`, `affectedReferences[0..*]: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgValidationReport` | `attribute` | `accepted: Boolean`, `findings[0..*]: RtgValidationFinding`, `evidence: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgValidationInputInvalid` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgValidationTrack` | `schema_object`, `constraint_network`, `migration_cutover` |
| `RtgValidationSeverity` | `blocking`, `warning`, `informational` |
| `RtgValidationTrackSelection` | `all`, `selected` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `ValidateRtgChangeBatchContractVerification` | `ValidateRtgChangeBatch` | `projectionSemantics`, `trackIsolation`, `validateRtgChangeBatchFailureSemantics` | `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py#ValidateRtgChangeBatchContractVerification` |
| `ValidateRtgGraphStateContractVerification` | `ValidateRtgGraphState` | `validateRtgGraphStateFailureSemantics` | `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py#ValidateRtgGraphStateContractVerification` |
| `RtgChangeValidationBoundaryVerification` | `RtgChangeValidator` | `referenceSemantics`, `validationRuleCatalog`, `validationRules`, `reportSemantics`, `noMutation`, `deterministicReports`, `findingsComprehensive`, `sourceOfTruthExternal`, `blockingFindingsControlAcceptance`, `findingsAgentActionable`, `tracksExtractable`, `batchSectionsExplicit`, `constraintSchemaCompatibility`, `patternEvaluationDelegated`, `cascadeEffectsFromPreview` | `components/rtg/change_validation/tests/test_rtg_change_validation_contract.py#RtgChangeValidationBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
