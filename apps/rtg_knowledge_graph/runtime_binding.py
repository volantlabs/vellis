from __future__ import annotations

from collections.abc import Callable

from apps.rtg_knowledge_graph.mcp_toolset import (
    TOOL_NAMES,
    RtgMcpToolset,
    VellisRequestInvalid,
    runtime_fault_boundary,
)
from components.rtg.change_validation import RtgValidationInputInvalid
from components.rtg.controller import (
    RtgControllerApplyFailed,
    RtgControllerDiscoveryFailed,
    RtgControllerObjectNotFound,
    RtgControllerPreconditionFailed,
    RtgControllerRecoveryIndeterminate,
    RtgControllerSnapshotFailed,
    RtgControllerValidationFailed,
)
from components.rtg.migration import RtgMigrationNotFound, RtgMigrationStatusInvalid
from components.rtg.query import RtgQuerySpecInvalid, RtgQueryUnsupported
from components.runtime.component_adapter import (
    MethodBindingSpec,
    MutableAdapterHost,
    RuntimeActionIdempotency,
    create_typed_component_adapter,
    create_typed_proxy,
)
from components.runtime.message_runtime import (
    MessageRuntime,
    RuntimeAddress,
    RuntimeFailStopped,
    RuntimeLedgerUnavailable,
    RuntimeReplayIncompatible,
    RuntimeReplayMode,
    RuntimeTraceDisposition,
)

FACADE_CONTRACT_ID = "application.vellis.facade"
FACADE_BINDING_ID = "binding.python.vellis.facade.v1"


_FAILURES: dict[str, tuple[type[Exception], ...]] = {
    "rtg_get_system_state": (VellisRequestInvalid, RtgControllerDiscoveryFailed),
    "rtg_get_usage_guide": (VellisRequestInvalid,),
    "rtg_stage_schema_migration": (
        VellisRequestInvalid,
        RtgControllerValidationFailed,
        RtgControllerPreconditionFailed,
        RtgControllerApplyFailed,
    ),
    "rtg_validate_live_anchor_records": (
        VellisRequestInvalid,
        RtgControllerPreconditionFailed,
        RtgValidationInputInvalid,
    ),
    "rtg_apply_live_anchor_records": (
        VellisRequestInvalid,
        RtgControllerValidationFailed,
        RtgControllerApplyFailed,
    ),
    "rtg_validate_live_graph_changes": (
        VellisRequestInvalid,
        RtgControllerPreconditionFailed,
        RtgValidationInputInvalid,
    ),
    "rtg_apply_live_graph_changes": (
        VellisRequestInvalid,
        RtgControllerValidationFailed,
        RtgControllerApplyFailed,
    ),
    "rtg_stage_knowledge_changes": (
        VellisRequestInvalid,
        RtgControllerValidationFailed,
        RtgControllerPreconditionFailed,
        RtgControllerApplyFailed,
    ),
    "rtg_apply_migration_cutover": (
        VellisRequestInvalid,
        RtgControllerValidationFailed,
        RtgControllerPreconditionFailed,
        RtgControllerApplyFailed,
        RtgControllerRecoveryIndeterminate,
    ),
    "rtg_abandon_migration": (
        VellisRequestInvalid,
        RtgControllerPreconditionFailed,
        RtgControllerApplyFailed,
    ),
    "rtg_execute_query": (VellisRequestInvalid, RtgQuerySpecInvalid, RtgQueryUnsupported),
    "rtg_resolve_anchor_by_fact": (
        VellisRequestInvalid,
        RtgQuerySpecInvalid,
        RtgQueryUnsupported,
    ),
    "rtg_get_object": (VellisRequestInvalid, RtgControllerObjectNotFound),
    "rtg_list_migrations": (VellisRequestInvalid, RtgMigrationStatusInvalid),
    "rtg_get_migration": (VellisRequestInvalid, RtgMigrationNotFound),
    "rtg_validate_graph": (VellisRequestInvalid, RtgControllerValidationFailed),
    "rtg_discover_anchor_types": (VellisRequestInvalid, RtgControllerDiscoveryFailed),
    "rtg_get_schema_pack": (VellisRequestInvalid, RtgControllerDiscoveryFailed),
    "rtg_export_system_snapshot": (RtgControllerSnapshotFailed,),
    "rtg_persist_system_snapshot": (VellisRequestInvalid, RtgControllerSnapshotFailed),
    "rtg_list_persisted_snapshots": (RtgControllerSnapshotFailed,),
    "rtg_load_persisted_snapshot": (VellisRequestInvalid, RtgControllerSnapshotFailed),
    "rtg_replay_ledger": (
        VellisRequestInvalid,
        RuntimeReplayIncompatible,
        RuntimeLedgerUnavailable,
        RuntimeFailStopped,
    ),
    "rtg_verify_replay_from_ledger": (
        VellisRequestInvalid,
        RuntimeReplayIncompatible,
        RuntimeLedgerUnavailable,
        RuntimeFailStopped,
    ),
    "rtg_list_migration_history": (RuntimeLedgerUnavailable, RuntimeFailStopped),
    "rtg_flush_ledger_failures": (RuntimeLedgerUnavailable,),
    "rtg_restore_from_snapshot": (
        VellisRequestInvalid,
        RtgControllerSnapshotFailed,
        RtgControllerRecoveryIndeterminate,
    ),
}


def _failure_trace_dispositions(
    tool_name: str,
) -> tuple[tuple[type[Exception], RuntimeTraceDisposition], ...]:
    if tool_name == "rtg_apply_migration_cutover":
        return (
            (RtgControllerValidationFailed, RuntimeTraceDisposition.COMMITTED),
            (RtgControllerApplyFailed, RuntimeTraceDisposition.COMMITTED),
            (RtgControllerRecoveryIndeterminate, RuntimeTraceDisposition.INDETERMINATE),
        )
    if tool_name == "rtg_restore_from_snapshot":
        return (
            (RtgControllerRecoveryIndeterminate, RuntimeTraceDisposition.INDETERMINATE),
        )
    return ()


_ALL_FAILURES = tuple(
    dict.fromkeys(failure for failures in _FAILURES.values() for failure in failures)
)
_SPECS = tuple(
    MethodBindingSpec(
        tool_name,
        RuntimeReplayMode.COORDINATOR_TRACE,
        RuntimeActionIdempotency.UNSPECIFIED,
        recovery_authorized=tool_name == "rtg_replay_ledger",
        failure_types=_FAILURES[tool_name],
        failure_trace_dispositions=_failure_trace_dispositions(tool_name),
    )
    for tool_name in TOOL_NAMES
)


class _RuntimeFaultFacade:
    """Dynamic view that lets the adapter observe failures before MCP shaping."""

    def __init__(self, resolve: Callable[[], RtgMcpToolset]) -> None:
        self._resolve = resolve

    def __getattr__(self, name: str) -> Callable[..., object]:
        method = getattr(self._resolve(), name, None)
        if not callable(method):
            raise AttributeError(name)

        def invoke(*args: object, **kwargs: object) -> object:
            current = getattr(self._resolve(), name, None)
            if not callable(current):
                raise AttributeError(name)
            with runtime_fault_boundary():
                return current(*args, **kwargs)

        return invoke
def create_vellis_facade_adapter(
    toolset: RtgMcpToolset | MutableAdapterHost[RtgMcpToolset],
):
    resolve = toolset.resolve if isinstance(toolset, MutableAdapterHost) else lambda: toolset
    return create_typed_component_adapter(
        _RuntimeFaultFacade(resolve),
        RtgMcpToolset,
        component_contract_id=FACADE_CONTRACT_ID,
        binding_id=FACADE_BINDING_ID,
        specs=_SPECS,
        failure_types=_ALL_FAILURES,
    )


def create_vellis_facade_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> RtgMcpToolset:
    return create_typed_proxy(
        runtime,
        source,
        target,
        RtgMcpToolset,
        component_contract_id=FACADE_CONTRACT_ID,
        specs=_SPECS,
        failure_types=_ALL_FAILURES,
    )
