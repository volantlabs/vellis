from __future__ import annotations

from components.rtg.change_validation.protocol import RtgValidationInputInvalid
from components.rtg.controller.protocol import (
    RtgControllerApplyFailed,
    RtgControllerDiscoveryFailed,
    RtgControllerError,
    RtgControllerObjectNotFound,
    RtgControllerPreconditionFailed,
    RtgControllerRecoveryIndeterminate,
    RtgControllerSnapshotFailed,
    RtgControllerValidationFailed,
)
from components.rtg.migration.protocol import (
    RtgMigrationNotFound,
    RtgMigrationStatusInvalid,
)
from components.rtg.query.protocol import RtgQuerySpecInvalid, RtgQueryUnsupported
from components.runtime.component_adapter import (
    ComponentAdapter,
    create_action_catalog,
    load_runtime_binding_resource,
)

CONTROLLER_FAILURES: dict[str, tuple[type[Exception], ...]] = {
    "apply_live_graph_changes": (
        RtgControllerValidationFailed,
        RtgControllerApplyFailed,
        RtgControllerRecoveryIndeterminate,
    ),
    "validate_live_graph_changes": (
        RtgControllerPreconditionFailed,
        RtgValidationInputInvalid,
    ),
    "stage_knowledge_changes": (
        RtgControllerValidationFailed,
        RtgControllerPreconditionFailed,
        RtgControllerApplyFailed,
        RtgControllerRecoveryIndeterminate,
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
    "list_schema_definitions_by_type_key": (RtgControllerPreconditionFailed,),
    "get_system_state": (RtgControllerDiscoveryFailed,),
    "export_system_snapshot": (RtgControllerSnapshotFailed,),
    "persist_system_snapshot": (RtgControllerSnapshotFailed,),
    "list_persisted_snapshots": (RtgControllerSnapshotFailed,),
    "load_persisted_snapshot": (RtgControllerSnapshotFailed,),
    "abandon_migration": (
        RtgControllerPreconditionFailed,
        RtgControllerApplyFailed,
        RtgControllerRecoveryIndeterminate,
    ),
    "restore_from_snapshot": (
        RtgControllerSnapshotFailed,
        RtgControllerRecoveryIndeterminate,
    ),
}

CONTROLLER_RUNTIME_BINDING = load_runtime_binding_resource(
    __package__,
    failure_types=CONTROLLER_FAILURES,
)
RTG_CONTROLLER_ACTIONS = create_action_catalog(CONTROLLER_RUNTIME_BINDING)


def create_rtg_controller_adapter(coordinator: object) -> ComponentAdapter:
    create_adapter = getattr(coordinator, "create_adapter", None)
    if not callable(create_adapter):
        raise TypeError("controller coordinator must provide create_adapter()")
    adapter = create_adapter()
    if not isinstance(adapter, ComponentAdapter):
        raise TypeError("controller coordinator returned a non-standard adapter")
    return adapter


__all__ = [
    "CONTROLLER_RUNTIME_BINDING",
    "CONTROLLER_FAILURES",
    "RTG_CONTROLLER_ACTIONS",
    "create_rtg_controller_adapter",
    "RtgControllerError",
]
