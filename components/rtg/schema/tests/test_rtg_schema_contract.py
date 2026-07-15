from __future__ import annotations

import copy
from uuid import UUID, uuid4

import pytest

from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgIdentityCriterion,
    RtgLinkSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaDefinitionInvalid,
    RtgSchemaDefinitionKindInvalid,
    RtgSchemaDirectionInvalid,
    RtgSchemaField,
    RtgSchemaLiveTypeConflict,
    RtgSchemaPayloadInvalid,
    RtgSchemaSnapshot,
    RtgSchemaSnapshotInvalid,
    RtgSchemaTypeKeyInvalid,
    RtgSchemaUuidConflict,
)
from components.rtg.schema.reference import create_reference_component


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


MODEL_EVIDENCE = {
    "PutSchemaDefinitionContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_live_type_key_uniqueness_allows_non_live_candidates",
        "test_recursive_fields_require_coherent_unique_kind_sets",
        "test_schema_field_refinements_are_normalized_and_reject_invalid_combinations",
        "test_allowed_values_preserve_distinct_large_json_integers",
        "test_schema_payload_sets_are_unique_disjoint_and_canonical",
        "test_schema_failure_vocabulary_is_boundary_specific",
        "test_node_definitions_require_time_shape_and_links_reject_it",
        "test_state_as_of_requires_interval_fields_and_reserved_system_fields_are_rejected",
        "test_node_identity_criteria_are_stored_and_snapshotted",
        "test_identity_criteria_reject_invalid_shape_and_payload_paths",
        "test_link_definitions_reject_identity_criteria",
        "test_link_definitions_require_link_kind_and_validate_enum",
    ),
    "DeleteSchemaDefinitionContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_schema_failure_vocabulary_is_boundary_specific",
    ),
    "ExportSchemaSnapshotContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_schema_field_refinements_are_normalized_and_reject_invalid_combinations",
        "test_schema_snapshot_rejects_duplicate_and_coercive_input",
    ),
    "GetSchemaDefinitionContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_link_participation_distinguishes_query_and_result_directions",
        "test_schema_pack_selection_is_unique_and_ordered",
    ),
    "ListSchemaDefinitionsContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_link_participation_distinguishes_query_and_result_directions",
        "test_schema_snapshot_rejects_duplicate_and_coercive_input",
    ),
    "ListDefinitionsByTypeKeyContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_link_participation_distinguishes_query_and_result_directions",
        "test_schema_snapshot_rejects_duplicate_and_coercive_input",
    ),
    "ListAnchorDataTypeKeysContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_live_type_key_uniqueness_allows_non_live_candidates",
        "test_schema_payload_sets_are_unique_disjoint_and_canonical",
        "test_schema_snapshot_rejects_duplicate_and_coercive_input",
    ),
    "ListLinkParticipationContractVerification": (
        "test_link_participation_distinguishes_query_and_result_directions",
    ),
    "ListAnchorTypeSummariesContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_live_type_key_uniqueness_allows_non_live_candidates",
        "test_link_participation_distinguishes_query_and_result_directions",
        "test_schema_payload_sets_are_unique_disjoint_and_canonical",
        "test_schema_failure_vocabulary_is_boundary_specific",
        "test_schema_snapshot_rejects_duplicate_and_coercive_input",
        "test_schema_pack_selection_is_unique_and_ordered",
    ),
    "GetSchemaPackContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_schema_pack_selection_is_unique_and_ordered",
    ),
    "CreateEmptyRtgSchemaContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
    ),
    "ImportRtgSchemaSnapshotContractVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_schema_field_refinements_are_normalized_and_reject_invalid_combinations",
        "test_schema_snapshot_rejects_duplicate_and_coercive_input",
    ),
    "RetrofitSchemaSnapshotLinkKindsContractVerification": (
        "test_legacy_snapshot_link_kind_retrofit_defaults_missing_links",
    ),
    "RtgSchemaBoundaryVerification": (
        "test_schema_stores_definitions_snapshots_and_schema_packs",
        "test_live_type_key_uniqueness_allows_non_live_candidates",
        "test_link_participation_distinguishes_query_and_result_directions",
        "test_recursive_fields_require_coherent_unique_kind_sets",
        "test_schema_field_refinements_are_normalized_and_reject_invalid_combinations",
        "test_allowed_values_preserve_distinct_large_json_integers",
        "test_schema_payload_sets_are_unique_disjoint_and_canonical",
        "test_schema_failure_vocabulary_is_boundary_specific",
        "test_schema_snapshot_rejects_duplicate_and_coercive_input",
        "test_schema_pack_selection_is_unique_and_ordered",
        "test_node_definitions_require_time_shape_and_links_reject_it",
        "test_state_as_of_requires_interval_fields_and_reserved_system_fields_are_rejected",
        "test_node_identity_criteria_are_stored_and_snapshotted",
        "test_identity_criteria_reject_invalid_shape_and_payload_paths",
        "test_link_definitions_reject_identity_criteria",
        "test_link_definitions_require_link_kind_and_validate_enum",
        "test_legacy_snapshot_link_kind_retrofit_defaults_missing_links",
    ),
}


def test_schema_stores_definitions_snapshots_and_schema_packs() -> None:
    schema = create_reference_component()
    person = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="A person anchor.",
            payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
            time_shape="state_now",
        )
    )
    profile = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="Person profile data.",
            payload=RtgDataObjectSchemaPayload(
                properties={
                    "name": RtgSchemaField(required=True, value_kinds=("string",)),
                }
            ),
            time_shape="state_now",
        )
    )
    attended = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="link",
            type_key="attended",
            description="Attendance link.",
            payload=RtgLinkSchemaPayload(
                allowed_source_types=("Person",),
                allowed_target_types=("Meeting",),
                link_kind="semantic",
            ),
        )
    )

    pack = schema.get_schema_pack(("Person",))
    restored = InMemoryRtgSchema.import_snapshot(schema.export_snapshot())

    assert pack.anchor_schemas == (person,)
    assert pack.associated_data_object_schemas == (profile,)
    assert pack.link_schemas == (attended,)
    assert restored.get_definition(concrete_uuid(person.uuid)).type_key == "Person"


def test_live_type_key_uniqueness_allows_non_live_candidates() -> None:
    schema = create_reference_component()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Component",
            description="Live component.",
            payload=RtgAnchorSchemaPayload(),
            time_shape="state_now",
        )
    )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Component",
            description="Replacement candidate.",
            payload=RtgAnchorSchemaPayload(),
            time_shape="state_now",
            system={"live": False},
        )
    )

    with pytest.raises(RtgSchemaLiveTypeConflict):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="data_object",
                type_key="Component",
                description="Conflicting live type.",
                payload=RtgDataObjectSchemaPayload(),
                time_shape="state_now",
            )
        )


def test_link_participation_distinguishes_query_and_result_directions() -> None:
    schema = create_reference_component()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="link",
            type_key="related",
            description="A link that admits Person at either endpoint.",
            payload=RtgLinkSchemaPayload(
                allowed_source_types=("Person",),
                allowed_target_types=("Person", "Project"),
                link_kind="semantic",
            ),
        )
    )

    assert schema.list_link_participation("Project").links[0].direction == "target"
    assert schema.list_link_participation("Person", "source").links[0].direction == "both"
    assert schema.list_link_participation("Person", "target").links[0].direction == "both"
    assert schema.list_link_participation("Person", "either").links[0].direction == "both"
    with pytest.raises(RtgSchemaDirectionInvalid):
        schema.list_link_participation("Person", "both")


def test_recursive_fields_require_coherent_unique_kind_sets() -> None:
    schema = create_reference_component()
    stored = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="A profile with recursive contact data.",
            payload=RtgDataObjectSchemaPayload(
                properties={
                    "contact": RtgSchemaField(
                        required=True,
                        value_kinds=("uuid", "string", "number", "integer", "object"),
                        properties={
                            "label": RtgSchemaField(
                                required=True,
                                value_kinds=("string",),
                            )
                        },
                    )
                }
            ),
            time_shape="state_now",
        )
    )
    assert isinstance(stored.payload, RtgDataObjectSchemaPayload)
    assert stored.payload.properties["contact"].value_kinds == (
        "string",
        "integer",
        "number",
        "object",
        "uuid",
    )

    incoherent_fields = (
        RtgSchemaField(
            required=True,
            value_kinds=("string",),
            properties={"nested": RtgSchemaField(True, ("string",))},
        ),
        RtgSchemaField(
            required=True,
            value_kinds=("string",),
            items=RtgSchemaField(True, ("string",)),
        ),
        RtgSchemaField(required=True, value_kinds=("string", "string")),
    )
    for index, field in enumerate(incoherent_fields):
        with pytest.raises(RtgSchemaPayloadInvalid):
            schema.put_definition(
                RtgSchemaDefinition(
                    uuid=uuid4(),
                    kind="data_object",
                    type_key=f"Invalid{index}",
                    description="An intentionally invalid recursive field.",
                    payload=RtgDataObjectSchemaPayload(properties={"field": field}),
                    time_shape="state_now",
                )
            )


def test_schema_field_refinements_are_normalized_and_reject_invalid_combinations() -> None:
    schema = create_reference_component()
    stored = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="PlanFacts",
            description="Facts with reusable semantic field refinements.",
            payload=RtgDataObjectSchemaPayload(
                properties={
                    "status": RtgSchemaField(True, ("string",), allowed_values=("next", "waiting")),
                    "due": RtgSchemaField(True, ("string",), format="date"),
                    "score": RtgSchemaField(True, ("number",), minimum=0, maximum=1),
                    "code": RtgSchemaField(True, ("string",), pattern=r"^[A-Z]+$"),
                }
            ),
            time_shape="state_now",
        )
    )
    assert isinstance(stored.payload, RtgDataObjectSchemaPayload)
    assert stored.payload.properties["status"].allowed_values == ("next", "waiting")
    assert InMemoryRtgSchema.import_snapshot(schema.export_snapshot()).export_snapshot() == (
        schema.export_snapshot()
    )

    invalid_fields = (
        RtgSchemaField(True, ("string",), allowed_values=("same", "same")),
        RtgSchemaField(True, ("string",), minimum=0),
        RtgSchemaField(True, ("number",), minimum=2, maximum=1),
        RtgSchemaField(True, ("number",), format="date"),
        RtgSchemaField(True, ("string",), pattern="(?=unsupported)"),
    )
    for index, field in enumerate(invalid_fields):
        with pytest.raises(RtgSchemaPayloadInvalid):
            schema.put_definition(
                RtgSchemaDefinition(
                    uuid=uuid4(),
                    kind="data_object",
                    type_key=f"InvalidRefinement{index}",
                    description="Invalid refinement probe.",
                    payload=RtgDataObjectSchemaPayload(properties={"value": field}),
                    time_shape="state_now",
                )
            )


def test_allowed_values_preserve_distinct_large_json_integers() -> None:
    schema = create_reference_component()
    values = (10**40 + 1, 10**40 + 2)

    stored = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="LargeIntegerFacts",
            description="Facts with exact large integer alternatives.",
            payload=RtgDataObjectSchemaPayload(
                properties={"value": RtgSchemaField(True, ("integer",), allowed_values=values)}
            ),
            time_shape="state_now",
        )
    )

    assert isinstance(stored.payload, RtgDataObjectSchemaPayload)
    assert stored.payload.properties["value"].allowed_values == values


def test_schema_payload_sets_are_unique_disjoint_and_canonical() -> None:
    schema = create_reference_component()
    stored_anchor = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="A person with associated data.",
            payload=RtgAnchorSchemaPayload(
                required_data_types=("Zulu", "Alpha"),
                optional_data_types=("Middle",),
            ),
            time_shape="state_now",
        )
    )
    assert isinstance(stored_anchor.payload, RtgAnchorSchemaPayload)
    assert stored_anchor.payload.required_data_types == ("Alpha", "Zulu")

    with pytest.raises(RtgSchemaPayloadInvalid):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="anchor",
                type_key="Duplicate",
                description="Duplicate membership is invalid.",
                payload=RtgAnchorSchemaPayload(required_data_types=("Profile", "Profile")),
                time_shape="state_now",
            )
        )
    with pytest.raises(RtgSchemaPayloadInvalid):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="anchor",
                type_key="Overlap",
                description="Required and optional membership must be disjoint.",
                payload=RtgAnchorSchemaPayload(
                    required_data_types=("Profile",),
                    optional_data_types=("Profile",),
                ),
                time_shape="state_now",
            )
        )


def test_schema_failure_vocabulary_is_boundary_specific() -> None:
    schema = create_reference_component()
    base = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Person",
        description="A person.",
        payload=RtgAnchorSchemaPayload(),
    )
    with pytest.raises(RtgSchemaDefinitionKindInvalid):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=base.uuid,
                kind="unsupported",
                type_key=base.type_key,
                description=base.description,
                payload=base.payload,
            )
        )
    with pytest.raises(RtgSchemaTypeKeyInvalid):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=base.uuid,
                kind=base.kind,
                type_key=" bad ",
                description=base.description,
                payload=base.payload,
            )
        )
    with pytest.raises(RtgSchemaDefinitionInvalid):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=base.uuid,
                kind="link",
                type_key=base.type_key,
                description=base.description,
                payload=base.payload,
            )
        )
    with pytest.raises(RtgSchemaDefinitionInvalid):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=base.uuid,
                kind=base.kind,
                type_key=base.type_key,
                description="",
                payload=base.payload,
            )
        )


def test_schema_snapshot_rejects_duplicate_and_coercive_input() -> None:
    schema = create_reference_component()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="A profile.",
            payload=RtgDataObjectSchemaPayload(
                properties={"name": RtgSchemaField(required=False, value_kinds=("string",))}
            ),
            time_shape="state_now",
        )
    )
    record = schema.export_snapshot().definitions[0]
    with pytest.raises(RtgSchemaUuidConflict):
        InMemoryRtgSchema.import_snapshot(RtgSchemaSnapshot(definitions=(record, record)))

    malformed = copy.deepcopy(record)
    payload = malformed["payload"]
    assert isinstance(payload, dict)
    properties = payload["properties"]
    assert isinstance(properties, dict)
    name_field = properties["name"]
    assert isinstance(name_field, dict)
    name_field["required"] = "false"
    with pytest.raises(RtgSchemaPayloadInvalid):
        InMemoryRtgSchema.import_snapshot(RtgSchemaSnapshot(definitions=(malformed,)))
    with pytest.raises(RtgSchemaSnapshotInvalid):
        InMemoryRtgSchema.import_snapshot(RtgSchemaSnapshot(definitions=({"kind": "anchor"},)))


def test_schema_pack_selection_is_unique_and_ordered() -> None:
    schema = create_reference_component()
    for type_key in ("Alpha", "Zulu"):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="anchor",
                type_key=type_key,
                description=f"{type_key} anchor.",
                payload=RtgAnchorSchemaPayload(),
                time_shape="state_now",
            )
        )
    assert [item.type_key for item in schema.get_schema_pack(("Zulu", "Alpha")).anchor_schemas] == [
        "Zulu",
        "Alpha",
    ]
    with pytest.raises(RtgSchemaTypeKeyInvalid):
        schema.get_schema_pack(("Alpha", "Alpha"))


def test_node_definitions_require_time_shape_and_links_reject_it() -> None:
    schema = create_reference_component()

    with pytest.raises(RtgSchemaPayloadInvalid, match="time_shape"):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="anchor",
                type_key="Person",
                description="A person anchor.",
                payload=RtgAnchorSchemaPayload(),
            )
        )

    anchor = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="A person anchor.",
            payload=RtgAnchorSchemaPayload(),
            time_shape="state_now",
        )
    )
    event = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="ProfileVersion",
            description="Immutable profile version.",
            payload=RtgDataObjectSchemaPayload(
                properties={"name": RtgSchemaField(required=True, value_kinds=("string",))}
            ),
            time_shape="event",
        )
    )

    with pytest.raises(RtgSchemaPayloadInvalid, match="time_shape"):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="link",
                type_key="knows",
                description="Person knows person.",
                payload=RtgLinkSchemaPayload(
                    allowed_source_types=("Person",),
                    allowed_target_types=("Person",),
                    link_kind="semantic",
                ),
                time_shape="state_now",
            )
        )

    restored = InMemoryRtgSchema.import_snapshot(schema.export_snapshot())

    assert anchor.time_shape == "state_now"
    assert event.time_shape == "event"
    assert restored.get_definition(concrete_uuid(event.uuid)).time_shape == "event"


def test_node_identity_criteria_are_stored_and_snapshotted() -> None:
    schema = create_reference_component()
    anchor_identity = RtgIdentityCriterion(
        criterion_key="person_display_name",
        property_paths=("display_name",),
        match_strategy="normalized",
        scope="same_type",
    )
    data_identity = RtgIdentityCriterion(
        criterion_key="profile_name",
        property_paths=("properties.name",),
        match_strategy="exact",
        scope="same_type",
    )

    person = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="A person anchor.",
            payload=RtgAnchorSchemaPayload(),
            time_shape="state_now",
            identity_criteria=(anchor_identity,),
        )
    )
    profile = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="Person profile data.",
            payload=RtgDataObjectSchemaPayload(
                properties={"name": RtgSchemaField(required=True, value_kinds=("string",))}
            ),
            time_shape="state_now",
            identity_criteria=(data_identity,),
        )
    )

    snapshot = schema.export_snapshot()
    restored = InMemoryRtgSchema.import_snapshot(snapshot)

    assert person.identity_criteria == (anchor_identity,)
    assert profile.identity_criteria == (data_identity,)
    assert restored.get_definition(concrete_uuid(person.uuid)).identity_criteria == (
        anchor_identity,
    )
    assert restored.get_definition(concrete_uuid(profile.uuid)).identity_criteria == (
        data_identity,
    )
    assert any("identity_criteria" in record for record in snapshot.definitions)


def test_identity_criteria_reject_invalid_shape_and_payload_paths() -> None:
    schema = create_reference_component()

    invalid_cases = (
        (
            RtgIdentityCriterion("", ("display_name",), "exact", "same_type"),
            RtgAnchorSchemaPayload(),
            "criterion_key",
        ),
        (
            RtgIdentityCriterion("person_name", (), "exact", "same_type"),
            RtgAnchorSchemaPayload(),
            "property_paths",
        ),
        (
            RtgIdentityCriterion("person_name", ("display_name",), "fuzzy", "same_type"),
            RtgAnchorSchemaPayload(),
            "match_strategy",
        ),
        (
            RtgIdentityCriterion("person_name", ("display_name",), "exact", "global"),
            RtgAnchorSchemaPayload(),
            "scope",
        ),
        (
            RtgIdentityCriterion("person_name", ("",), "exact", "same_type"),
            RtgAnchorSchemaPayload(),
            "property_paths",
        ),
        (
            RtgIdentityCriterion("profile_email", ("properties.email",), "exact", "same_type"),
            RtgDataObjectSchemaPayload(
                properties={"name": RtgSchemaField(required=True, value_kinds=("string",))}
            ),
            "properties.email",
        ),
    )
    for criterion, payload, match in invalid_cases:
        with pytest.raises(RtgSchemaPayloadInvalid, match=match):
            schema.put_definition(
                RtgSchemaDefinition(
                    uuid=uuid4(),
                    kind="anchor"
                    if isinstance(payload, RtgAnchorSchemaPayload)
                    else "data_object",
                    type_key=f"Type{uuid4().hex}",
                    description="Invalid identity criterion.",
                    payload=payload,
                    time_shape="state_now",
                    identity_criteria=(criterion,),
                )
            )


def test_link_definitions_reject_identity_criteria() -> None:
    schema = create_reference_component()

    with pytest.raises(RtgSchemaPayloadInvalid, match="identity_criteria"):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="link",
                type_key="knows",
                description="Person knows person.",
                payload=RtgLinkSchemaPayload(
                    allowed_source_types=("Person",),
                    allowed_target_types=("Person",),
                    link_kind="semantic",
                ),
                identity_criteria=(
                    RtgIdentityCriterion(
                        criterion_key="unsupported_link_identity",
                        property_paths=("type",),
                        match_strategy="exact",
                        scope="same_type",
                    ),
                ),
            )
        )


def test_link_definitions_require_link_kind_and_validate_enum() -> None:
    schema = create_reference_component()

    with pytest.raises(RtgSchemaPayloadInvalid, match="link_kind"):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="link",
                type_key="knows",
                description="Person knows person.",
                payload=RtgLinkSchemaPayload(
                    allowed_source_types=("Person",),
                    allowed_target_types=("Person",),
                ),
            )
        )

    with pytest.raises(RtgSchemaPayloadInvalid, match="link_kind"):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="link",
                type_key="knows",
                description="Person knows person.",
                payload=RtgLinkSchemaPayload(
                    allowed_source_types=("Person",),
                    allowed_target_types=("Person",),
                    link_kind="mystery",
                ),
            )
        )

    stored = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="link",
            type_key="knows",
            description="Person knows person.",
            payload=RtgLinkSchemaPayload(
                allowed_source_types=("Person",),
                allowed_target_types=("Person",),
                link_kind="semantic",
            ),
        )
    )

    assert isinstance(stored.payload, RtgLinkSchemaPayload)
    assert stored.payload.link_kind == "semantic"


def test_legacy_snapshot_link_kind_retrofit_defaults_missing_links() -> None:
    link_uuid = uuid4()
    snapshot = RtgSchemaSnapshot(
        definitions=(
            {
                "uuid": str(link_uuid),
                "kind": "link",
                "type_key": "knows",
                "description": "Person knows person.",
                "payload": {
                    "allowed_source_types": ["Person"],
                    "allowed_target_types": ["Person"],
                },
                "system": {"live": True},
            },
        )
    )

    result = InMemoryRtgSchema.retrofit_snapshot_link_kinds(snapshot, default_kind="semantic")
    restored = InMemoryRtgSchema.import_snapshot(result.snapshot)
    restored_link = restored.get_definition(link_uuid)

    assert isinstance(restored_link.payload, RtgLinkSchemaPayload)
    assert restored_link.payload.link_kind == "semantic"
    assert result.report.defaulted_link_definitions[0].definition_uuid == link_uuid
    assert result.report.defaulted_link_definitions[0].type_key == "knows"
    assert result.report.defaulted_link_definitions[0].link_kind == "semantic"


def test_state_as_of_requires_interval_fields_and_reserved_system_fields_are_rejected() -> None:
    schema = create_reference_component()

    with pytest.raises(RtgSchemaPayloadInvalid, match="valid_from"):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="data_object",
                type_key="Employment",
                description="Employment state over time.",
                payload=RtgDataObjectSchemaPayload(
                    properties={
                        "valid_from": RtgSchemaField(required=True, value_kinds=("string",)),
                        "valid_to": RtgSchemaField(
                            required=True, value_kinds=("string",), format="date_time"
                        ),
                    }
                ),
                time_shape="state_as_of",
            )
        )

    with pytest.raises(RtgSchemaPayloadInvalid, match="created_at"):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="data_object",
                type_key="BadProfile",
                description="Attempts to own kernel timestamps.",
                payload=RtgDataObjectSchemaPayload(
                    properties={
                        "created_at": RtgSchemaField(
                            required=True, value_kinds=("string",), format="date_time"
                        )
                    }
                ),
                time_shape="state_now",
            )
        )

    stored = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Employment",
            description="Employment state over time.",
            payload=RtgDataObjectSchemaPayload(
                properties={
                    "valid_from": RtgSchemaField(
                        required=True, value_kinds=("string",), format="date_time"
                    ),
                    "valid_to": RtgSchemaField(
                        required=True, value_kinds=("string",), format="date_time"
                    ),
                    "title": RtgSchemaField(required=False, value_kinds=("string",)),
                }
            ),
            time_shape="state_as_of",
        )
    )

    assert stored.time_shape == "state_as_of"
