from __future__ import annotations

import dataclasses
from typing import cast
from uuid import UUID, uuid4

from components.rtg.change_validation.protocol import (
    RtgChangeBatch,
    RtgChangeReference,
    RtgConstraintChangeSet,
    RtgConstraintDefinitionWrite,
    RtgGraphAnchorWrite,
    RtgGraphAssociationChange,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
    RtgGraphLinkWrite,
    RtgGraphLiveStatusChange,
    RtgLiveStatusChange,
    RtgMigrationChangeSet,
    RtgMigrationEvidenceAddition,
    RtgMigrationRecordWrite,
    RtgMigrationStatusChange,
    RtgSchemaChangeSet,
    RtgSchemaDefinitionWrite,
)
from components.rtg.constraints.protocol import RtgConstraintLiveStatusChange
from components.rtg.controller.protocol import RtgControllerPreconditionFailed
from components.rtg.graph.protocol import JsonObject, RtgObject
from components.rtg.migration.protocol import RtgMigrationCutoverPlan


def resolve_batch_with_generated_ids(
    batch: RtgChangeBatch,
) -> tuple[RtgChangeBatch, dict[str, UUID]]:
    """Resolve local references without consulting or mutating component state."""

    resolved: dict[str, UUID | str] = {}
    generated_ids: dict[str, UUID] = {}

    def resolve_uuid(ref: RtgChangeReference) -> UUID:
        if isinstance(ref.resource_id, UUID):
            return ref.resource_id
        if isinstance(ref.resource_id, str):
            return UUID(ref.resource_id)
        if ref.local_ref is None:
            raise RtgControllerPreconditionFailed("missing local reference")
        if ref.local_ref not in resolved:
            generated = uuid4()
            resolved[ref.local_ref] = generated
            generated_ids[ref.local_ref] = generated
        value = resolved[ref.local_ref]
        if not isinstance(value, UUID):
            raise RtgControllerPreconditionFailed("local reference kind mismatch")
        return value

    def resolve_migration_id(ref: RtgChangeReference) -> str:
        if ref.resource_id is not None:
            return str(ref.resource_id)
        if ref.local_ref is None:
            raise RtgControllerPreconditionFailed("missing migration local reference")
        if ref.local_ref not in resolved:
            generated = uuid4()
            resolved[ref.local_ref] = str(generated)
            generated_ids[ref.local_ref] = generated
        value = resolved[ref.local_ref]
        if not isinstance(value, str):
            raise RtgControllerPreconditionFailed("local reference kind mismatch")
        return value

    graph_changes = RtgGraphChangeSet(
        anchor_writes=tuple(
            RtgGraphAnchorWrite(
                RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                write.type,
                write.display_name,
                write.system,
            )
            for write in batch.graph_changes.anchor_writes
        ),
        data_object_writes=tuple(
            RtgGraphDataObjectWrite(
                RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                write.type,
                write.properties,
                write.system,
                tuple(
                    RtgChangeReference(resource_id=resolve_uuid(ref)) for ref in write.anchor_refs
                ),
            )
            for write in batch.graph_changes.data_object_writes
        ),
        link_writes=tuple(
            RtgGraphLinkWrite(
                RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                write.type,
                RtgChangeReference(resource_id=resolve_uuid(write.source_ref)),
                RtgChangeReference(resource_id=resolve_uuid(write.target_ref)),
                write.system,
            )
            for write in batch.graph_changes.link_writes
        ),
        associate_data=tuple(
            RtgGraphAssociationChange(
                RtgChangeReference(resource_id=resolve_uuid(change.anchor_ref)),
                RtgChangeReference(resource_id=resolve_uuid(change.data_ref)),
            )
            for change in batch.graph_changes.associate_data
        ),
        dissociate_data=tuple(
            RtgGraphAssociationChange(
                RtgChangeReference(resource_id=resolve_uuid(change.anchor_ref)),
                RtgChangeReference(resource_id=resolve_uuid(change.data_ref)),
            )
            for change in batch.graph_changes.dissociate_data
        ),
        delete_anchors=tuple(
            RtgChangeReference(resource_id=resolve_uuid(ref))
            for ref in batch.graph_changes.delete_anchors
        ),
        delete_data_objects=tuple(
            RtgChangeReference(resource_id=resolve_uuid(ref))
            for ref in batch.graph_changes.delete_data_objects
        ),
        delete_links=tuple(
            RtgChangeReference(resource_id=resolve_uuid(ref))
            for ref in batch.graph_changes.delete_links
        ),
        set_live=tuple(
            RtgGraphLiveStatusChange(
                RtgChangeReference(resource_id=resolve_uuid(change.object_ref)),
                change.live,
            )
            for change in batch.graph_changes.set_live
        ),
    )
    schema_changes = RtgSchemaChangeSet(
        definition_writes=tuple(
            RtgSchemaDefinitionWrite(
                RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                dataclasses.replace(write.definition, uuid=resolve_uuid(write.ref)),
            )
            for write in batch.schema_changes.definition_writes
        ),
        delete_definitions=tuple(
            RtgChangeReference(resource_id=resolve_uuid(ref))
            for ref in batch.schema_changes.delete_definitions
        ),
        set_live=tuple(
            RtgLiveStatusChange(
                RtgChangeReference(resource_id=resolve_uuid(change.target_ref)),
                change.live,
            )
            for change in batch.schema_changes.set_live
        ),
    )
    constraint_changes = RtgConstraintChangeSet(
        constraint_writes=tuple(
            RtgConstraintDefinitionWrite(
                RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                dataclasses.replace(write.constraint, uuid=resolve_uuid(write.ref)),
            )
            for write in batch.constraint_changes.constraint_writes
        ),
        delete_constraints=tuple(
            RtgChangeReference(resource_id=resolve_uuid(ref))
            for ref in batch.constraint_changes.delete_constraints
        ),
        set_live=tuple(
            RtgConstraintLiveStatusChange(
                RtgChangeReference(resource_id=resolve_uuid(change.target_ref)),
                change.live,
            )
            for change in batch.constraint_changes.set_live
        ),
    )
    migration_changes = RtgMigrationChangeSet(
        migration_writes=tuple(
            RtgMigrationRecordWrite(
                RtgChangeReference(resource_id=resolve_migration_id(write.ref)),
                dataclasses.replace(
                    write.migration,
                    migration_id=resolve_migration_id(write.ref),
                ),
            )
            for write in batch.migration_changes.migration_writes
        ),
        delete_migrations=tuple(
            RtgChangeReference(resource_id=resolve_migration_id(ref))
            for ref in batch.migration_changes.delete_migrations
        ),
        status_changes=tuple(
            RtgMigrationStatusChange(
                RtgChangeReference(resource_id=resolve_migration_id(change.migration_ref)),
                change.status,
                change.status_metadata,
            )
            for change in batch.migration_changes.status_changes
        ),
        evidence_additions=tuple(
            RtgMigrationEvidenceAddition(
                RtgChangeReference(resource_id=resolve_migration_id(change.migration_ref)),
                change.evidence,
            )
            for change in batch.migration_changes.evidence_additions
        ),
    )
    return (
        RtgChangeBatch(graph_changes, schema_changes, constraint_changes, migration_changes),
        generated_ids,
    )


def validate_live_graph_lane(graph_changes: RtgGraphChangeSet) -> None:
    for write in (
        *graph_changes.anchor_writes,
        *graph_changes.data_object_writes,
        *graph_changes.link_writes,
    ):
        if write.system.get("live", True) is not True:
            raise RtgControllerPreconditionFailed(
                "live graph lane cannot create non-live graph candidates"
            )
    if any(change.live is not True for change in graph_changes.set_live):
        raise RtgControllerPreconditionFailed("live graph lane cannot make graph objects non-live")


def validate_knowledge_lane(batch: RtgChangeBatch) -> None:
    if batch.graph_changes.set_live:
        raise RtgControllerPreconditionFailed("knowledge staging cannot apply graph live flips")
    if batch.schema_changes.set_live or batch.constraint_changes.set_live:
        raise RtgControllerPreconditionFailed(
            "knowledge staging cannot apply schema or constraint live flips"
        )
    if batch.schema_changes.delete_definitions or batch.constraint_changes.delete_constraints:
        raise RtgControllerPreconditionFailed(
            "knowledge staging cannot delete schema or constraint definitions"
        )
    migrations = tuple(write.migration for write in batch.migration_changes.migration_writes)
    allowed = {
        "schema": {item for migration in migrations for item in migration.schema_make_live},
        "constraints": {
            item for migration in migrations for item in migration.constraint_make_live
        },
        "graph": {item for migration in migrations for item in migration.graph_make_live},
    }
    for write in batch.schema_changes.definition_writes:
        if write.definition.system.get("live", True) is not False:
            raise RtgControllerPreconditionFailed(
                "knowledge staging schema definitions must be non-live candidates"
            )
        if uuid_ref(write.ref) not in allowed["schema"]:
            raise RtgControllerPreconditionFailed(
                "staged schema definitions must be referenced by a migration"
            )
    for write in batch.constraint_changes.constraint_writes:
        if write.constraint.system.get("live", True) is not False:
            raise RtgControllerPreconditionFailed(
                "knowledge staging constraints must be non-live candidates"
            )
        if uuid_ref(write.ref) not in allowed["constraints"]:
            raise RtgControllerPreconditionFailed(
                "staged constraints must be referenced by a migration"
            )
    for write in (
        *batch.graph_changes.anchor_writes,
        *batch.graph_changes.data_object_writes,
        *batch.graph_changes.link_writes,
    ):
        if write.system.get("live", True) is not False:
            raise RtgControllerPreconditionFailed(
                "knowledge staging graph writes must be non-live candidates"
            )
        if uuid_ref(write.ref) not in allowed["graph"]:
            raise RtgControllerPreconditionFailed(
                "staged graph candidates must be referenced by a migration"
            )


def change_batch_from_cutover_plan(plan: RtgMigrationCutoverPlan) -> RtgChangeBatch:
    return RtgChangeBatch(
        graph_changes=RtgGraphChangeSet(
            set_live=tuple(
                RtgGraphLiveStatusChange(RtgChangeReference(resource_id=item), live)
                for item, live in (
                    *((item, False) for item in plan.graph_make_non_live),
                    *((item, True) for item in plan.graph_make_live),
                )
            )
        ),
        schema_changes=RtgSchemaChangeSet(
            set_live=tuple(
                RtgLiveStatusChange(RtgChangeReference(resource_id=item), live)
                for item, live in (
                    *((item, False) for item in plan.schema_make_non_live),
                    *((item, True) for item in plan.schema_make_live),
                )
            )
        ),
        constraint_changes=RtgConstraintChangeSet(
            set_live=tuple(
                RtgConstraintLiveStatusChange(RtgChangeReference(resource_id=item), live)
                for item, live in (
                    *((item, False) for item in plan.constraint_make_non_live),
                    *((item, True) for item in plan.constraint_make_live),
                )
            )
        ),
    )


def operation_details(operation_name: str, batch: RtgChangeBatch) -> JsonObject:
    if operation_name != "stage_knowledge_changes" or not batch.migration_changes.migration_writes:
        return {}
    migrations = batch.migration_changes.migration_writes
    schema = [str(uuid_ref(item.ref)) for item in batch.schema_changes.definition_writes]
    constraints = [str(uuid_ref(item.ref)) for item in batch.constraint_changes.constraint_writes]
    graph = [
        str(uuid_ref(item.ref))
        for item in (
            *batch.graph_changes.anchor_writes,
            *batch.graph_changes.data_object_writes,
            *batch.graph_changes.link_writes,
        )
    ]
    return cast(
        JsonObject,
        {
            "operation_effect": "staged_candidates_written",
            "requires_cutover": any(
                item.migration.schema_make_live
                or item.migration.schema_make_non_live
                or item.migration.constraint_make_live
                or item.migration.constraint_make_non_live
                or item.migration.graph_make_live
                or item.migration.graph_make_non_live
                for item in migrations
            ),
            "staged_migration_ids": [item.migration.migration_id for item in migrations],
            "candidate_counts": {
                "schema": len(schema),
                "constraints": len(constraints),
                "graph": len(graph),
            },
            "candidate_ids": {"schema": schema, "constraints": constraints, "graph": graph},
        },
    )


def uuid_ref(ref: RtgChangeReference) -> UUID:
    if isinstance(ref.resource_id, UUID):
        return ref.resource_id
    if isinstance(ref.resource_id, str):
        return UUID(ref.resource_id)
    raise RtgControllerPreconditionFailed("reference is not resolved")


def text_ref(ref: RtgChangeReference) -> str:
    if ref.resource_id is not None:
        return str(ref.resource_id)
    if ref.local_ref is not None:
        return ref.local_ref
    raise RtgControllerPreconditionFailed("reference is not resolved")


def is_live(item: RtgObject | object) -> bool:
    system = getattr(item, "system", {})
    return isinstance(system, dict) and system.get("live", True) is True
