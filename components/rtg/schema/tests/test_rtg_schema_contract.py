from __future__ import annotations

import copy
from uuid import UUID, uuid4

import pytest

from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
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
        )
    )
    attended = schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="link",
            type_key="attended",
            description="Attendance link.",
            payload=RtgLinkSchemaPayload(
                allowed_source_types=("Person",), allowed_target_types=("Meeting",)
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
        )
    )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Component",
            description="Replacement candidate.",
            payload=RtgAnchorSchemaPayload(),
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
            )
        )
    assert [item.type_key for item in schema.get_schema_pack(("Zulu", "Alpha")).anchor_schemas] == [
        "Zulu",
        "Alpha",
    ]
    with pytest.raises(RtgSchemaTypeKeyInvalid):
        schema.get_schema_pack(("Alpha", "Alpha"))
