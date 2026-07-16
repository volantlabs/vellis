from __future__ import annotations

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
    ComponentAdapter,
    ReplayStateBinding,
    create_action_catalog,
    create_typed_component_adapter,
    load_runtime_binding_resource,
)

_CONTRACT = "component.rtg.constraints"
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
    "apply_batch": (
        RtgConstraintUuidInvalid,
        RtgConstraintUuidConflict,
        RtgConstraintKindInvalid,
        RtgConstraintDefinitionInvalid,
        RtgConstraintPayloadInvalid,
        RtgConstraintSystemValueInvalid,
        RtgConstraintNotFound,
    ),
    "count_summary": (),
    "put_constraint": (
        RtgConstraintUuidInvalid,
        RtgConstraintUuidConflict,
        RtgConstraintKindInvalid,
        RtgConstraintDefinitionInvalid,
        RtgConstraintPayloadInvalid,
        RtgConstraintSystemValueInvalid,
    ),
    "get_constraint": (RtgConstraintNotFound,),
    "list_constraints": (RtgConstraintKindInvalid, RtgConstraintPayloadInvalid),
    "list_constraints_by_target": (
        RtgConstraintTargetInvalid,
        RtgConstraintKindInvalid,
    ),
    "delete_constraint": (RtgConstraintNotFound,),
}
_RUNTIME_BINDING = load_runtime_binding_resource(__package__, failure_types=_FAILURES)
RTG_CONSTRAINTS_ACTIONS = create_action_catalog(_RUNTIME_BINDING)


def create_rtg_constraints_adapter(
    constraints: RtgConstraints,
    *,
    replay_state: ReplayStateBinding | None = None,
) -> ComponentAdapter:
    return create_typed_component_adapter(
        constraints,
        RtgConstraints,
        binding=_RUNTIME_BINDING,
        failure_types=(RtgConstraintError,),
        replay_state=replay_state,
    )
