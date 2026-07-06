from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgLinkSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaField,
    RtgSchemaLiveConflict,
)
from components.rtg.schema.reference import create_reference_component


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


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

    with pytest.raises(RtgSchemaLiveConflict):
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="data_object",
                type_key="Component",
                description="Conflicting live type.",
                payload=RtgDataObjectSchemaPayload(),
            )
        )
