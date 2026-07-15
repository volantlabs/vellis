from __future__ import annotations

from typing import Any

from components.rtg.constraints.protocol import (
    RtgConstraintDefinitionInvalid,
    RtgConstraintError,
    RtgConstraintKindInvalid,
    RtgConstraintNotFound,
    RtgConstraintPayloadInvalid,
    RtgConstraints,
    RtgConstraintSnapshotInvalid,
    RtgConstraintSystemValueInvalid,
    RtgConstraintTargetInvalid,
    RtgConstraintUuidConflict,
    RtgConstraintUuidInvalid,
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

_CONTRACT = "component.rtg.constraints"
_READ = RuntimeReplayMode.NO_STATE_EFFECT
_FAILURES: dict[str, tuple[type[RtgConstraintError], ...]] = {
    "export_snapshot": (),
    "replace_snapshot": (
        RtgConstraintSnapshotInvalid,
        RtgConstraintUuidInvalid,
        RtgConstraintUuidConflict,
        RtgConstraintKindInvalid,
        RtgConstraintDefinitionInvalid,
        RtgConstraintPayloadInvalid,
        RtgConstraintSystemValueInvalid,
    ),
    "put_constraint": (
        RtgConstraintUuidInvalid,
        RtgConstraintUuidConflict,
        RtgConstraintKindInvalid,
        RtgConstraintDefinitionInvalid,
        RtgConstraintPayloadInvalid,
        RtgConstraintSystemValueInvalid,
    ),
    "get_constraint": (RtgConstraintNotFound,),
    "list_constraints": (RtgConstraintKindInvalid,),
    "list_constraints_by_target": (
        RtgConstraintTargetInvalid,
        RtgConstraintKindInvalid,
    ),
    "delete_constraint": (RtgConstraintNotFound,),
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
        "put_constraint",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        resolved_argument_from_result="constraint",
        failure_types=_FAILURES["put_constraint"],
    ),
    MethodBindingSpec(
        "get_constraint",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["get_constraint"],
    ),
    MethodBindingSpec(
        "list_constraints",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list_constraints"],
    ),
    MethodBindingSpec(
        "list_constraints_by_target",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list_constraints_by_target"],
    ),
    MethodBindingSpec(
        "delete_constraint",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        failure_types=_FAILURES["delete_constraint"],
    ),
)


def create_rtg_constraints_adapter(
    constraints: RtgConstraints | MutableAdapterHost[Any],
    *,
    replay_state: ReplayStateBinding | None = None,
):
    return create_typed_component_adapter(
        constraints,
        RtgConstraints,
        component_contract_id=_CONTRACT,
        binding_id="binding.python.rtg.constraints.v1",
        specs=_SPECS,
        failure_types=(RtgConstraintError,),
        replay_state=replay_state,
    )


def create_rtg_constraints_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> RtgConstraints:
    return create_typed_proxy(
        runtime,
        source,
        target,
        RtgConstraints,
        component_contract_id=_CONTRACT,
        specs=_SPECS,
        failure_types=(RtgConstraintError,),
    )
