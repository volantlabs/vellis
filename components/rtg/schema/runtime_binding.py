from __future__ import annotations

from components.rtg.schema.protocol import (
    RtgSchema,
    RtgSchemaDefinitionInvalid,
    RtgSchemaDefinitionKindInvalid,
    RtgSchemaDefinitionNotFound,
    RtgSchemaDirectionInvalid,
    RtgSchemaError,
    RtgSchemaLiveTypeConflict,
    RtgSchemaPayloadInvalid,
    RtgSchemaSnapshotInvalid,
    RtgSchemaSystemValueInvalid,
    RtgSchemaTypeKeyInvalid,
    RtgSchemaUuidConflict,
    RtgSchemaUuidInvalid,
)
from components.runtime.component_adapter import (
    ComponentAdapter,
    ReplayStateBinding,
    create_action_catalog,
    create_typed_component_adapter,
    load_runtime_binding_resource,
)

_CONTRACT = "component.rtg.schema"
_FAILURES: dict[str, tuple[type[RtgSchemaError], ...]] = {
    "export_snapshot": (),
    "replace_snapshot": (
        RtgSchemaSnapshotInvalid,
        RtgSchemaUuidInvalid,
        RtgSchemaUuidConflict,
        RtgSchemaDefinitionKindInvalid,
        RtgSchemaTypeKeyInvalid,
        RtgSchemaDefinitionInvalid,
        RtgSchemaPayloadInvalid,
        RtgSchemaSystemValueInvalid,
        RtgSchemaLiveTypeConflict,
    ),
    "apply_batch": (
        RtgSchemaUuidInvalid,
        RtgSchemaUuidConflict,
        RtgSchemaDefinitionKindInvalid,
        RtgSchemaTypeKeyInvalid,
        RtgSchemaDefinitionInvalid,
        RtgSchemaPayloadInvalid,
        RtgSchemaSystemValueInvalid,
        RtgSchemaLiveTypeConflict,
        RtgSchemaDefinitionNotFound,
    ),
    "count_summary": (),
    "put_definition": (
        RtgSchemaUuidInvalid,
        RtgSchemaDefinitionKindInvalid,
        RtgSchemaTypeKeyInvalid,
        RtgSchemaDefinitionInvalid,
        RtgSchemaPayloadInvalid,
        RtgSchemaSystemValueInvalid,
        RtgSchemaLiveTypeConflict,
    ),
    "get_definition": (RtgSchemaDefinitionNotFound,),
    "list_definitions": (RtgSchemaDefinitionKindInvalid, RtgSchemaPayloadInvalid),
    "list_definitions_by_type_key": (
        RtgSchemaTypeKeyInvalid,
        RtgSchemaDefinitionKindInvalid,
        RtgSchemaPayloadInvalid,
    ),
    "list_anchor_data_type_keys": (
        RtgSchemaTypeKeyInvalid,
        RtgSchemaDefinitionNotFound,
    ),
    "list_link_participation": (
        RtgSchemaTypeKeyInvalid,
        RtgSchemaDirectionInvalid,
    ),
    "list_anchor_type_summaries": (),
    "get_schema_pack": (RtgSchemaTypeKeyInvalid, RtgSchemaDefinitionNotFound),
    "delete_definition": (RtgSchemaDefinitionNotFound,),
}
_RUNTIME_BINDING = load_runtime_binding_resource(__package__, failure_types=_FAILURES)
RTG_SCHEMA_ACTIONS = create_action_catalog(_RUNTIME_BINDING)


def create_rtg_schema_adapter(
    schema: RtgSchema,
    *,
    replay_state: ReplayStateBinding | None = None,
) -> ComponentAdapter:
    return create_typed_component_adapter(
        schema,
        RtgSchema,
        binding=_RUNTIME_BINDING,
        failure_types=(RtgSchemaError,),
        replay_state=replay_state,
    )
