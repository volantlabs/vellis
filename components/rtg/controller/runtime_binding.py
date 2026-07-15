from __future__ import annotations

from typing import cast

from components.rtg.change_validation.protocol import RtgValidationInputInvalid
from components.rtg.controller.protocol import (
    RtgController,
    RtgControllerApplyFailed,
    RtgControllerDiscoveryFailed,
    RtgControllerError,
    RtgControllerObjectNotFound,
    RtgControllerPreconditionFailed,
    RtgControllerRecoveryIndeterminate,
    RtgControllerSnapshotFailed,
    RtgControllerValidationFailed,
    RtgSystemSnapshot,
)
from components.rtg.migration.protocol import RtgMigrationNotFound, RtgMigrationStatusInvalid
from components.rtg.query.protocol import RtgQuerySpecInvalid, RtgQueryUnsupported
from components.runtime.component_adapter import (
    MethodBindingSpec,
    ReplayStateBinding,
    RuntimeActionIdempotency,
    create_typed_component_adapter,
    create_typed_proxy,
    decode_typed,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import (
    JsonObject,
    MessageRuntime,
    RuntimeAddress,
    RuntimeReplayMode,
    RuntimeTraceDisposition,
)

_CONTRACT = "component.rtg.controller"
_COORDINATOR = RuntimeReplayMode.COORDINATOR_TRACE
_READ_METHODS = {
    "validate_live_graph_changes",
    "execute_query",
    "get_object",
    "list_migrations",
    "get_migration",
    "validate_graph",
    "discover_anchor_types",
    "get_schema_pack",
    "get_system_state",
    "export_system_snapshot",
    "list_persisted_snapshots",
    "load_persisted_snapshot",
}
_METHODS = (
    "apply_live_graph_changes",
    "validate_live_graph_changes",
    "stage_knowledge_changes",
    "apply_migration_cutover",
    "execute_query",
    "get_object",
    "list_migrations",
    "get_migration",
    "validate_graph",
    "discover_anchor_types",
    "get_schema_pack",
    "get_system_state",
    "export_system_snapshot",
    "persist_system_snapshot",
    "list_persisted_snapshots",
    "load_persisted_snapshot",
    "abandon_migration",
    "restore_from_snapshot",
)
_FAILURES: dict[str, tuple[type[Exception], ...]] = {
    "apply_live_graph_changes": (
        RtgControllerValidationFailed,
        RtgControllerApplyFailed,
    ),
    "validate_live_graph_changes": (
        RtgControllerPreconditionFailed,
        RtgValidationInputInvalid,
    ),
    "stage_knowledge_changes": (
        RtgControllerValidationFailed,
        RtgControllerPreconditionFailed,
        RtgControllerApplyFailed,
    ),
    "apply_migration_cutover": (
        RtgControllerPreconditionFailed,
        RtgControllerValidationFailed,
        RtgControllerApplyFailed,
        RtgControllerRecoveryIndeterminate,
    ),
    "execute_query": (RtgQuerySpecInvalid, RtgQueryUnsupported),
    "get_object": (RtgControllerObjectNotFound,),
    "list_migrations": (RtgMigrationStatusInvalid,),
    "get_migration": (RtgMigrationNotFound,),
    "validate_graph": (RtgControllerValidationFailed,),
    "discover_anchor_types": (RtgControllerDiscoveryFailed,),
    "get_schema_pack": (RtgControllerDiscoveryFailed,),
    "get_system_state": (RtgControllerDiscoveryFailed,),
    "export_system_snapshot": (RtgControllerSnapshotFailed,),
    "persist_system_snapshot": (RtgControllerSnapshotFailed,),
    "list_persisted_snapshots": (RtgControllerSnapshotFailed,),
    "load_persisted_snapshot": (RtgControllerSnapshotFailed,),
    "abandon_migration": (
        RtgControllerPreconditionFailed,
        RtgControllerApplyFailed,
    ),
    "restore_from_snapshot": (
        RtgControllerSnapshotFailed,
        RtgControllerRecoveryIndeterminate,
    ),
}


def _build_failed_cutover_effect(component: object, _error: Exception) -> JsonObject:
    controller = cast(RtgController, component)
    return {
        "supersedes_trace_effects": True,
        "arguments": {"snapshot": encode_json(controller.export_system_snapshot())},
    }


def _apply_failed_cutover_effect(component: object, payload: JsonObject) -> object:
    if payload.get("supersedes_trace_effects") is not True:
        raise ValueError("failed-cutover effect must supersede derived trace effects")
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict) or "snapshot" not in arguments:
        raise ValueError("failed-cutover effect requires a coordinated snapshot")
    snapshot = cast(RtgSystemSnapshot, decode_typed(arguments["snapshot"], RtgSystemSnapshot))
    return cast(RtgController, component).restore_from_snapshot(snapshot)


def _build_restore_effect(
    _args: tuple[object, ...], kwargs: dict[str, object], _result: object
) -> JsonObject:
    return {
        "supersedes_trace_effects": True,
        "arguments": {"snapshot": encode_json(kwargs["snapshot"])},
    }


_SPECS = tuple(
    MethodBindingSpec(
        method,
        (RuntimeReplayMode.CANONICAL_EFFECT if method == "restore_from_snapshot" else _COORDINATOR),
        RuntimeActionIdempotency.IDEMPOTENT
        if method in _READ_METHODS
        else RuntimeActionIdempotency.NON_IDEMPOTENT,
        modeled_fault_trace_disposition=(
            RuntimeTraceDisposition.COMMITTED
            if method == "apply_migration_cutover"
            else RuntimeTraceDisposition.ABORTED
        ),
        failure_replay_effect_builder=(
            _build_failed_cutover_effect if method == "apply_migration_cutover" else None
        ),
        failure_replay_effect_applier=(
            _apply_failed_cutover_effect if method == "apply_migration_cutover" else None
        ),
        replay_effect_builder=(
            _build_restore_effect if method == "restore_from_snapshot" else None
        ),
        failure_types=_FAILURES[method],
        failure_trace_dispositions=(
            (
                RtgControllerPreconditionFailed,
                RuntimeTraceDisposition.ABORTED,
            ),
            (
                RtgControllerRecoveryIndeterminate,
                RuntimeTraceDisposition.INDETERMINATE,
            ),
        )
        if method == "apply_migration_cutover"
        else (
            (
                RtgControllerRecoveryIndeterminate,
                RuntimeTraceDisposition.INDETERMINATE,
            ),
        )
        if method == "restore_from_snapshot"
        else (),
        failure_replay_effect_types=(
            RtgControllerValidationFailed,
            RtgControllerApplyFailed,
        )
        if method == "apply_migration_cutover"
        else None,
    )
    for method in _METHODS
)


def create_rtg_controller_adapter(
    controller: RtgController, *, replay_state: ReplayStateBinding | None = None
):
    return create_typed_component_adapter(
        controller,
        RtgController,
        component_contract_id=_CONTRACT,
        binding_id="binding.python.rtg.controller.v1",
        specs=_SPECS,
        failure_types=(RtgControllerError,),
        replay_state=replay_state,
    )


def create_rtg_controller_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> RtgController:
    return create_typed_proxy(
        runtime,
        source,
        target,
        RtgController,
        component_contract_id=_CONTRACT,
        specs=_SPECS,
        failure_types=(
            RtgControllerError,
            RtgValidationInputInvalid,
            RtgMigrationNotFound,
            RtgMigrationStatusInvalid,
            RtgQuerySpecInvalid,
            RtgQueryUnsupported,
        ),
    )
