from __future__ import annotations

from typing import Any

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
    MethodBindingSpec,
    MutableAdapterHost,
    ReplayStateBinding,
    RuntimeActionIdempotency,
    create_typed_component_adapter,
    create_typed_proxy,
)
from components.runtime.message_runtime import MessageRuntime, RuntimeAddress, RuntimeReplayMode

_CONTRACT = "component.rtg.schema"
_READ = RuntimeReplayMode.NO_STATE_EFFECT
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
    "list_definitions": (RtgSchemaDefinitionKindInvalid,),
    "list_definitions_by_type_key": (
        RtgSchemaTypeKeyInvalid,
        RtgSchemaDefinitionKindInvalid,
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
_SPECS = (
    MethodBindingSpec(
        "export_snapshot",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["export_snapshot"],
    ),
    MethodBindingSpec(
        "replace_snapshot",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["replace_snapshot"],
    ),
    MethodBindingSpec(
        "put_definition",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        resolved_argument_from_result="definition",
        failure_types=_FAILURES["put_definition"],
    ),
    MethodBindingSpec(
        "get_definition",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["get_definition"],
    ),
    MethodBindingSpec(
        "list_definitions",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list_definitions"],
    ),
    MethodBindingSpec(
        "list_definitions_by_type_key",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list_definitions_by_type_key"],
    ),
    MethodBindingSpec(
        "list_anchor_data_type_keys",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list_anchor_data_type_keys"],
    ),
    MethodBindingSpec(
        "list_link_participation",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list_link_participation"],
    ),
    MethodBindingSpec(
        "list_anchor_type_summaries",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list_anchor_type_summaries"],
    ),
    MethodBindingSpec(
        "get_schema_pack",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["get_schema_pack"],
    ),
    MethodBindingSpec(
        "delete_definition",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        failure_types=_FAILURES["delete_definition"],
    ),
)


def create_rtg_schema_adapter(
    schema: RtgSchema | MutableAdapterHost[Any],
    *,
    replay_state: ReplayStateBinding | None = None,
):
    return create_typed_component_adapter(
        schema,
        RtgSchema,
        component_contract_id=_CONTRACT,
        binding_id="binding.python.rtg.schema.v1",
        specs=_SPECS,
        failure_types=(RtgSchemaError,),
        replay_state=replay_state,
    )


def create_rtg_schema_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> RtgSchema:
    return create_typed_proxy(
        runtime,
        source,
        target,
        RtgSchema,
        component_contract_id=_CONTRACT,
        specs=_SPECS,
        failure_types=(RtgSchemaError,),
    )
