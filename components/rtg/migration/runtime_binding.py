from __future__ import annotations

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
    ComponentAdapter,
    ReplayStateBinding,
    create_action_catalog,
    create_typed_component_adapter,
    load_runtime_binding_resource,
)

_CONTRACT = "component.rtg.migration"
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
    "apply_batch": (
        RtgMigrationIdInvalid,
        RtgMigrationIdConflict,
        RtgMigrationNotFound,
        RtgMigrationRecordInvalid,
        RtgMigrationStatusInvalid,
        RtgMigrationStatusTransitionInvalid,
        RtgMigrationEvidenceInvalid,
        RtgMigrationDeleteNotAllowed,
    ),
    "count_summary": (),
    "find_candidate_owners": (RtgMigrationRecordInvalid,),
    "put_migration": (
        RtgMigrationIdInvalid,
        RtgMigrationRecordInvalid,
        RtgMigrationStatusInvalid,
        RtgMigrationStatusTransitionInvalid,
        RtgMigrationEvidenceInvalid,
    ),
    "get_migration": (RtgMigrationNotFound,),
    "list_migrations": (RtgMigrationStatusInvalid, RtgMigrationRecordInvalid),
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
_RUNTIME_BINDING = load_runtime_binding_resource(__package__, failure_types=_FAILURES)
RTG_MIGRATION_ACTIONS = create_action_catalog(_RUNTIME_BINDING)


def create_rtg_migration_adapter(
    migration: RtgMigration,
    *,
    replay_state: ReplayStateBinding | None = None,
) -> ComponentAdapter:
    return create_typed_component_adapter(
        migration,
        RtgMigration,
        binding=_RUNTIME_BINDING,
        failure_types=(RtgMigrationError,),
        replay_state=replay_state,
    )
