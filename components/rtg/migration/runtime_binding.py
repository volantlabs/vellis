from __future__ import annotations

from typing import Any

from components.rtg.migration.protocol import (
    RtgMigration,
    RtgMigrationDeleteNotAllowed,
    RtgMigrationError,
    RtgMigrationEvidenceInvalid,
    RtgMigrationIdConflict,
    RtgMigrationIdInvalid,
    RtgMigrationNotFound,
    RtgMigrationRecordInvalid,
    RtgMigrationSnapshotInvalid,
    RtgMigrationStatusInvalid,
    RtgMigrationStatusTransitionInvalid,
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

_CONTRACT = "component.rtg.migration"
_READ = RuntimeReplayMode.NO_STATE_EFFECT
_FAILURES: dict[str, tuple[type[RtgMigrationError], ...]] = {
    "export_snapshot": (),
    "replace_snapshot": (
        RtgMigrationSnapshotInvalid,
        RtgMigrationIdInvalid,
        RtgMigrationIdConflict,
        RtgMigrationRecordInvalid,
        RtgMigrationStatusInvalid,
        RtgMigrationEvidenceInvalid,
    ),
    "put_migration": (
        RtgMigrationIdInvalid,
        RtgMigrationRecordInvalid,
        RtgMigrationStatusInvalid,
        RtgMigrationStatusTransitionInvalid,
        RtgMigrationEvidenceInvalid,
    ),
    "get_migration": (RtgMigrationNotFound,),
    "list_migrations": (RtgMigrationStatusInvalid,),
    "set_status": (
        RtgMigrationIdInvalid,
        RtgMigrationNotFound,
        RtgMigrationRecordInvalid,
        RtgMigrationStatusInvalid,
        RtgMigrationStatusTransitionInvalid,
    ),
    "add_evidence": (RtgMigrationNotFound, RtgMigrationEvidenceInvalid),
    "delete_migration": (
        RtgMigrationIdInvalid,
        RtgMigrationNotFound,
        RtgMigrationDeleteNotAllowed,
    ),
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
        "put_migration",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        resolved_argument_from_result="migration",
        failure_types=_FAILURES["put_migration"],
    ),
    MethodBindingSpec(
        "get_migration",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["get_migration"],
    ),
    MethodBindingSpec(
        "list_migrations",
        _READ,
        RuntimeActionIdempotency.IDEMPOTENT,
        failure_types=_FAILURES["list_migrations"],
    ),
    MethodBindingSpec(
        "set_status",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        failure_types=_FAILURES["set_status"],
    ),
    MethodBindingSpec(
        "add_evidence",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        failure_types=_FAILURES["add_evidence"],
    ),
    MethodBindingSpec(
        "delete_migration",
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        failure_types=_FAILURES["delete_migration"],
    ),
)


def create_rtg_migration_adapter(
    migration: RtgMigration | MutableAdapterHost[Any],
    *,
    replay_state: ReplayStateBinding | None = None,
):
    return create_typed_component_adapter(
        migration,
        RtgMigration,
        component_contract_id=_CONTRACT,
        binding_id="binding.python.rtg.migration.v1",
        specs=_SPECS,
        failure_types=(RtgMigrationError,),
        replay_state=replay_state,
    )


def create_rtg_migration_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> RtgMigration:
    return create_typed_proxy(
        runtime,
        source,
        target,
        RtgMigration,
        component_contract_id=_CONTRACT,
        specs=_SPECS,
        failure_types=(RtgMigrationError,),
    )
