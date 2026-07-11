from __future__ import annotations

from uuid import UUID, uuid4

from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    RtgChangeBatch,
    RtgChangeReference,
    RtgConstraintChangeSet,
    RtgGraphAnchorWrite,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
    RtgGraphLinkWrite,
    RtgMigrationChangeSet,
    RtgMigrationRecordWrite,
    RtgSchemaChangeSet,
    RtgSchemaDefinitionWrite,
    RtgValidationOptions,
)
from components.rtg.constraints import (
    InMemoryRtgConstraints,
    RtgConstraintDefinition,
    RtgConstraintQueryPatternPayload,
)
from components.rtg.graph import InMemoryRtgGraph, RtgAnchor, RtgDataObject
from components.rtg.migration import (
    InMemoryRtgMigration,
    RtgMigrationRecord,
    RtgMigrationReplacement,
)
from components.rtg.query import SimpleRtgQueryEngine
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaField,
)


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


def build_schema() -> InMemoryRtgSchema:
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="Person.",
            payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
        )
    )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="Profile.",
            payload=RtgDataObjectSchemaPayload(
                properties={"name": RtgSchemaField(required=True, value_kinds=("string",))}
            ),
        )
    )
    return schema


def test_validation_reports_schema_object_findings_without_mutation() -> None:
    graph = InMemoryRtgGraph.empty()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    data = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Profile", properties={"extra": "nope"}),
        (concrete_uuid(anchor.uuid),),
    )
    before = graph.export_snapshot()

    report = DeterministicRtgChangeValidator().validate_graph_state(
        graph,
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        SimpleRtgQueryEngine(),
    )

    assert report.accepted is False
    assert {finding.code for finding in report.findings} == {
        "schema_object.missing_required_property",
        "schema_object.undeclared_property",
    }
    missing = next(
        finding
        for finding in report.findings
        if finding.code == "schema_object.missing_required_property"
    )
    assert missing.diagnostic["category"] == "validation_failure"
    assert missing.diagnostic["path"] == "Profile.properties.name"
    assert graph.export_snapshot() == before
    stored = graph.get_object(concrete_uuid(data.uuid))
    assert isinstance(stored, RtgDataObject)
    assert stored.properties == {"extra": "nope"}


def test_schema_value_kind_refinements_and_nested_strictness() -> None:
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="Person.",
            payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
        )
    )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="Profile with refined scalar and nested fields.",
            payload=RtgDataObjectSchemaPayload(
                properties={
                    "amount": RtgSchemaField(required=True, value_kinds=("number",)),
                    "identifier": RtgSchemaField(required=True, value_kinds=("uuid",)),
                    "label": RtgSchemaField(required=True, value_kinds=("string",)),
                    "nested": RtgSchemaField(
                        required=True,
                        value_kinds=("object",),
                        properties={
                            "child": RtgSchemaField(required=True, value_kinds=("string",))
                        },
                    ),
                }
            ),
        )
    )
    graph = InMemoryRtgGraph.empty()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    identifier = str(uuid4())
    data = graph.put_data_object(
        RtgDataObject(
            uuid=uuid4(),
            type="Profile",
            properties={
                "amount": 1,
                "identifier": identifier,
                "label": identifier,
                "nested": {"child": "valid"},
            },
        ),
        (concrete_uuid(anchor.uuid),),
    )
    validator = DeterministicRtgChangeValidator()
    report = validator.validate_graph_state(
        graph,
        schema,
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        SimpleRtgQueryEngine(),
    )
    assert report.accepted is True

    graph.put_data_object(
        RtgDataObject(
            uuid=data.uuid,
            type="Profile",
            properties={
                "amount": 1,
                "identifier": identifier,
                "label": identifier,
                "nested": {"child": "valid", "undeclared": True},
            },
        ),
        (concrete_uuid(anchor.uuid),),
    )
    report = validator.validate_graph_state(
        graph,
        schema,
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        SimpleRtgQueryEngine(),
    )
    assert report.accepted is False
    assert "schema_object.property_kind_mismatch" in {finding.code for finding in report.findings}


def test_validation_rejects_malformed_proposed_data_batch() -> None:
    batch = RtgChangeBatch(
        graph_changes=RtgGraphChangeSet(
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=uuid4()),
                    type="Profile",
                    properties={"extra": "nope"},
                    anchor_refs=(RtgChangeReference(resource_id=uuid4()),),
                ),
            )
        )
    )

    report = DeterministicRtgChangeValidator().validate_batch(
        InMemoryRtgGraph.empty(),
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        SimpleRtgQueryEngine(),
        batch,
    )

    assert report.accepted is False
    assert "schema_object.undeclared_property" in {finding.code for finding in report.findings}


def test_unselected_malformed_sections_do_not_affect_selected_track() -> None:
    report = DeterministicRtgChangeValidator().validate_batch(
        InMemoryRtgGraph.empty(),
        build_schema(),
        object(),
        None,
        object(),
        RtgChangeBatch(
            constraint_changes=RtgConstraintChangeSet(
                delete_constraints=(RtgChangeReference(),)
            )
        ),
        RtgValidationOptions(tracks=("schema_object",)),
    )

    assert report.accepted is True
    assert report.findings == ()


def test_duplicate_findings_collapse_before_evidence_and_acceptance() -> None:
    graph = InMemoryRtgGraph.empty()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    for _ in range(2):
        graph.put_data_object(
            RtgDataObject(uuid=uuid4(), type="Profile", properties={}),
            (concrete_uuid(anchor.uuid),),
        )

    report = DeterministicRtgChangeValidator().validate_graph_state(
        graph,
        build_schema(),
        InMemoryRtgConstraints.empty(),
        None,
        SimpleRtgQueryEngine(),
        validation_options=RtgValidationOptions(tracks=("schema_object",)),
    )

    assert report.accepted is False
    assert [finding.code for finding in report.findings] == [
        "schema_object.missing_required_property"
    ]
    assert report.evidence["total_finding_count"] == 1


def test_unevaluable_constraint_payload_is_a_catalog_finding() -> None:
    constraints = InMemoryRtgConstraints.empty()
    constraints.put_constraint(
        RtgConstraintDefinition(
            uuid=uuid4(),
            kind="query_pattern",
            target_type_keys=("Person",),
            display_name="Malformed query",
            description="The public payload is structurally valid but cannot be evaluated.",
            payload=RtgConstraintQueryPatternPayload(
                query_spec={"not": "an RtgQuerySpec"},
                expectation="must_match_none",
            ),
        )
    )

    report = DeterministicRtgChangeValidator().validate_graph_state(
        InMemoryRtgGraph.empty(),
        build_schema(),
        constraints,
        None,
        SimpleRtgQueryEngine(),
        validation_options=RtgValidationOptions(tracks=("constraint_network",)),
    )

    assert [finding.code for finding in report.findings] == [
        "constraint_network.constraint_payload_unevaluable"
    ]


def test_validation_reports_unresolved_link_endpoints_with_paths() -> None:
    report = DeterministicRtgChangeValidator().validate_batch(
        InMemoryRtgGraph.empty(),
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        SimpleRtgQueryEngine(),
        RtgChangeBatch(
            graph_changes=RtgGraphChangeSet(
                link_writes=(
                    RtgGraphLinkWrite(
                        ref=RtgChangeReference(resource_id=uuid4()),
                        type="supports",
                        source_ref=RtgChangeReference(resource_id=uuid4()),
                        target_ref=RtgChangeReference(resource_id=uuid4()),
                    ),
                )
            )
        ),
    )

    messages = " ".join(finding.message for finding in report.findings)
    suggestions = " ".join(finding.suggestion or "" for finding in report.findings)
    assert report.accepted is False
    assert "schema_object.reference_missing" in {finding.code for finding in report.findings}
    assert "graph_changes.link_writes[0].source_ref" in messages
    assert "graph_changes.link_writes[0].target_ref" in messages
    assert "lookup_examples" in suggestions
    reference_findings = [
        finding for finding in report.findings if finding.code == "schema_object.reference_missing"
    ]
    assert all(
        finding.diagnostic["category"] == "reference_resolution" for finding in reference_findings
    )
    for finding in reference_findings:
        guide_topics = finding.diagnostic["guide_topics"]
        assert isinstance(guide_topics, list)
        assert "lookup_examples" in guide_topics


def test_migration_projection_reports_wrong_live_state() -> None:
    schema = build_schema()
    live_person = schema.list_definitions_by_type_key("Person", kind="anchor").definitions[0]
    migration = InMemoryRtgMigration.empty()
    migration.put_migration(
        RtgMigrationRecord(
            migration_id="already-live",
            description="Invalidly make an already-live schema live.",
            status="ready",
            schema_make_live=(concrete_uuid(live_person.uuid),),
        )
    )

    report = DeterministicRtgChangeValidator().validate_graph_state(
        InMemoryRtgGraph.empty(),
        schema,
        InMemoryRtgConstraints.empty(),
        migration,
        SimpleRtgQueryEngine(),
        migration_ids=("already-live",),
    )

    assert report.accepted is False
    assert "migration_cutover.wrong_live_state" in {finding.code for finding in report.findings}


def test_migration_projection_reports_replacement_type_mismatch_as_warning() -> None:
    schema = build_schema()
    live_person = schema.list_definitions_by_type_key("Person", kind="anchor").definitions[0]
    project_candidate = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Project",
        description="Project.",
        payload=RtgAnchorSchemaPayload(),
        system={"live": False},
    )
    schema.put_definition(project_candidate)
    migration = InMemoryRtgMigration.empty()
    migration.put_migration(
        RtgMigrationRecord(
            migration_id="person-to-project",
            description="Replace Person schema with Project schema.",
            status="ready",
            schema_make_live=(concrete_uuid(project_candidate.uuid),),
            schema_make_non_live=(concrete_uuid(live_person.uuid),),
            schema_replacements=(
                RtgMigrationReplacement(
                    concrete_uuid(live_person.uuid),
                    concrete_uuid(project_candidate.uuid),
                ),
            ),
        )
    )

    report = DeterministicRtgChangeValidator().validate_graph_state(
        InMemoryRtgGraph.empty(),
        schema,
        InMemoryRtgConstraints.empty(),
        migration,
        SimpleRtgQueryEngine(),
        migration_ids=("person-to-project",),
    )

    replacement_findings = [
        finding
        for finding in report.findings
        if finding.code == "migration_cutover.replacement_type_mismatch"
    ]
    assert report.accepted is True
    assert [finding.severity for finding in replacement_findings] == ["warning"]


def test_finding_limit_does_not_hide_blocking_acceptance() -> None:
    schema = build_schema()
    live_person = schema.list_definitions_by_type_key("Person", kind="anchor").definitions[0]
    live_profile = schema.list_definitions_by_type_key(
        "Profile", kind="data_object"
    ).definitions[0]
    project_candidate = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Project",
        description="Project.",
        payload=RtgAnchorSchemaPayload(),
        system={"live": False},
    )
    schema.put_definition(project_candidate)
    migration = InMemoryRtgMigration.empty()
    migration.put_migration(
        RtgMigrationRecord(
            migration_id="limited-findings",
            description="Produce both blocking and warning cutover findings.",
            status="ready",
            schema_make_live=(
                concrete_uuid(project_candidate.uuid),
                concrete_uuid(live_profile.uuid),
            ),
            schema_make_non_live=(concrete_uuid(live_person.uuid),),
            schema_replacements=(
                RtgMigrationReplacement(
                    concrete_uuid(live_person.uuid),
                    concrete_uuid(project_candidate.uuid),
                ),
            ),
        )
    )

    report = DeterministicRtgChangeValidator().validate_graph_state(
        InMemoryRtgGraph.empty(),
        schema,
        InMemoryRtgConstraints.empty(),
        migration,
        SimpleRtgQueryEngine(),
        migration_ids=("limited-findings",),
        validation_options=RtgValidationOptions(finding_limit=1),
    )

    assert report.accepted is False
    assert len(report.findings) == 1
    assert report.findings[0].severity == "blocking"
    assert report.findings[0].code == "migration_cutover.wrong_live_state"
    assert report.evidence["finding_count"] == 1
    assert report.evidence["total_finding_count"] == 2
    assert report.evidence["truncated"] is True


def test_staged_migration_batch_validates_projected_cutover_state() -> None:
    schema = build_schema()
    live_profile = schema.list_definitions_by_type_key(
        "Profile",
        kind="data_object",
    ).definitions[0]
    replacement_profile = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="data_object",
        type_key="Profile",
        description="Profile with numeric age.",
        payload=RtgDataObjectSchemaPayload(
            properties={"age": RtgSchemaField(required=True, value_kinds=("integer",))}
        ),
        system={"live": False},
    )
    person_uuid = uuid4()
    profile_uuid = uuid4()
    batch = RtgChangeBatch(
        schema_changes=RtgSchemaChangeSet(
            definition_writes=(
                RtgSchemaDefinitionWrite(
                    ref=RtgChangeReference(resource_id=concrete_uuid(replacement_profile.uuid)),
                    definition=replacement_profile,
                ),
            )
        ),
        graph_changes=RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(resource_id=person_uuid),
                    type="Person",
                    system={"live": False},
                ),
            ),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=profile_uuid),
                    type="Profile",
                    properties={"age": "not an integer"},
                    system={"live": False},
                    anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                ),
            ),
        ),
        migration_changes=RtgMigrationChangeSet(
            migration_writes=(
                RtgMigrationRecordWrite(
                    ref=RtgChangeReference(resource_id="profile-schema-v2"),
                    migration=RtgMigrationRecord(
                        migration_id="profile-schema-v2",
                        description="Replace Profile and publish candidate data.",
                        status="ready",
                        schema_make_live=(concrete_uuid(replacement_profile.uuid),),
                        schema_make_non_live=(concrete_uuid(live_profile.uuid),),
                        graph_make_live=(person_uuid, profile_uuid),
                    ),
                ),
            )
        ),
    )

    report = DeterministicRtgChangeValidator().validate_batch(
        InMemoryRtgGraph.empty(),
        schema,
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        SimpleRtgQueryEngine(),
        batch,
    )

    assert report.accepted is False
    assert {finding.code for finding in report.findings} >= {
        "schema_object.property_kind_mismatch",
        "migration_cutover.post_state_invalid",
    }
    mismatch = next(
        finding
        for finding in report.findings
        if finding.code == "schema_object.property_kind_mismatch"
    )
    assert mismatch.diagnostic["category"] == "validation_failure"
    assert mismatch.diagnostic["guide_topics"] == [
        "workflow_patterns",
        "live_write",
        "schema_staging_minimal",
    ]
