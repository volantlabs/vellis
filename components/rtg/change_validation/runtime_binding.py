from __future__ import annotations

import asyncio
import dataclasses
import json
from typing import cast
from uuid import UUID

from components.rtg.change_validation.projection import (
    ValidationConstraintProjection,
    ValidationGraphProjection,
    ValidationMigrationProjection,
    ValidationSchemaProjection,
)
from components.rtg.change_validation.protocol import (
    RtgChangeBatch,
    RtgChangeValidator,
    RtgValidationInputInvalid,
    RtgValidationOptions,
)
from components.rtg.constraints import RTG_CONSTRAINTS_ACTIONS
from components.rtg.constraints.protocol import (
    RtgConstraintDefinition,
    RtgConstraintDefinitionList,
)
from components.rtg.graph import RTG_GRAPH_ACTIONS
from components.rtg.graph.protocol import (
    RtgAnchor,
    RtgAnchorList,
    RtgDataObject,
    RtgDataObjectList,
    RtgLink,
    RtgLinkList,
    RtgObject,
    RtgObjectList,
    RtgTypeCountList,
)
from components.rtg.migration import RTG_MIGRATION_ACTIONS
from components.rtg.migration.protocol import (
    RtgMigrationRecord,
    RtgMigrationRecordList,
)
from components.rtg.query import RTG_QUERY_ACTIONS
from components.rtg.query.protocol import (
    RtgQueryOptions,
    RtgQueryResult,
    RtgQuerySpec,
    RtgQuerySpecInvalid,
)
from components.rtg.schema import RTG_SCHEMA_ACTIONS
from components.rtg.schema.protocol import (
    RtgSchemaDefinition,
    RtgSchemaDefinitionList,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ComponentExecution,
    RuntimeRemoteFault,
    create_action_catalog,
    load_runtime_binding_resource,
    runtime_binding_descriptor,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.component_adapter.typed_binding import decode_typed

_FAILURES = {
    "validate_batch": (RtgValidationInputInvalid,),
    "validate_graph_state": (RtgValidationInputInvalid,),
}
_RUNTIME_BINDING = load_runtime_binding_resource(__package__, failure_types=_FAILURES)
RTG_CHANGE_VALIDATION_ACTIONS = create_action_catalog(_RUNTIME_BINDING)


def create_rtg_change_validator_adapter(
    validator: RtgChangeValidator,
    *,
    graph_instance_key: str = "vellis.graph.primary",
    schema_instance_key: str = "vellis.schema.primary",
    constraints_instance_key: str = "vellis.constraints.primary",
    migration_instance_key: str = "vellis.migration.primary",
    query_instance_key: str = "vellis.query.primary",
) -> ComponentAdapter:
    async def handle(
        _args: tuple[object, ...],
        kwargs: dict[str, object],
        execution: ComponentExecution,
    ) -> None:
        options = decode_typed(kwargs.get("validation_options"), RtgValidationOptions | None)
        change_batch = (
            decode_typed(kwargs["change_batch"], RtgChangeBatch)
            if "change_batch" in kwargs
            else None
        )
        graph, schema, constraints, migration = await _coherent_sources(
            execution,
            graph_instance_key=graph_instance_key,
            schema_instance_key=schema_instance_key,
            constraints_instance_key=constraints_instance_key,
            migration_instance_key=migration_instance_key,
            change_batch=change_batch,
        )
        query = await _recorded_query_engine(
            execution,
            constraints=constraints,
            migration=migration,
            change_batch=change_batch,
            query_instance_key=query_instance_key,
        )
        if "change_batch" in kwargs:
            result = await asyncio.to_thread(
                validator.validate_batch,
                graph,
                schema,
                constraints,
                migration,
                query,
                cast(RtgChangeBatch, change_batch),
                options,
            )
        else:
            result = await asyncio.to_thread(
                validator.validate_graph_state,
                graph,
                schema,
                constraints,
                migration,
                query,
                decode_typed(kwargs.get("migration_ids"), tuple[str, ...] | None),
                options,
            )
        await execution.complete(result)

    bindings = []
    for name in ("validate_batch", "validate_graph_state"):
        if name == "validate_batch":
            decode = lambda payload: (  # noqa: E731
                (),
                {
                    "change_batch": payload["change_batch"],
                    "validation_options": payload.get("validation_options"),
                },
            )
        else:
            decode = lambda payload: (  # noqa: E731
                (),
                {
                    "migration_ids": payload.get("migration_ids"),
                    "validation_options": payload.get("validation_options"),
                },
            )
        bindings.append(
            ActionBinding(
                descriptor=runtime_binding_descriptor(_RUNTIME_BINDING, name),
                handler=handle,
                decode_request=decode,
                encode_result=encode_json,
                failure_types=(RtgValidationInputInvalid,),
            )
        )
    return ComponentAdapter(tuple(bindings))


class _RecordedQueryEngine:
    def __init__(self, results: dict[str, RtgQueryResult]) -> None:
        self._results = results

    def execute(
        self,
        graph: object,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        del graph, query_options
        try:
            return self._results[_query_key(query_spec)]
        except KeyError as error:
            raise RtgQuerySpecInvalid("projected query was not planned") from error


async def _recorded_query_engine(
    execution: ComponentExecution,
    *,
    constraints: ValidationConstraintProjection,
    migration: ValidationMigrationProjection,
    change_batch: RtgChangeBatch | None,
    query_instance_key: str,
) -> _RecordedQueryEngine:
    specs = _query_specs(
        (constraints.list_constraints().constraints, migration.list_migrations().migrations)
    )
    if change_batch is not None:
        specs.update(_query_specs(change_batch))
    results: dict[str, RtgQueryResult] = {}
    target = execution.address_for(query_instance_key)
    for index, spec in enumerate(sorted(specs.values(), key=_query_key)):
        arguments: dict[str, object] = {"query_spec": spec, "query_options": None}
        action = RTG_QUERY_ACTIONS["execute"]
        if change_batch is not None:
            action = RTG_QUERY_ACTIONS["execute_projected"]
            arguments["graph_changes"] = encode_json(change_batch.graph_changes)
        value = await execution.call(
            f"validation-query-{index}",
            action,
            arguments,
            target=target,
        )
        results[_query_key(spec)] = decode_typed(value, RtgQueryResult)
    return _RecordedQueryEngine(results)


def _query_specs(value: object) -> dict[str, RtgQuerySpec]:
    found: dict[str, RtgQuerySpec] = {}

    def visit(item: object) -> None:
        if isinstance(item, RtgQuerySpec):
            found[_query_key(item)] = item
        elif dataclasses.is_dataclass(item) and not isinstance(item, type):
            for field in dataclasses.fields(item):
                visit(getattr(item, field.name))
        elif isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, (tuple, list)):
            for nested in item:
                visit(nested)

    visit(value)
    return found


def _query_key(value: RtgQuerySpec) -> str:
    return json.dumps(encode_json(value), sort_keys=True, separators=(",", ":"))


async def _sparse_batch_sources(
    execution: ComponentExecution,
    change_batch: RtgChangeBatch,
    *,
    graph_instance_key: str,
    schema_instance_key: str,
    constraints_instance_key: str,
    migration_instance_key: str,
) -> tuple[
    ValidationGraphProjection,
    ValidationSchemaProjection,
    ValidationConstraintProjection,
    ValidationMigrationProjection,
]:
    """Read only records touched by the batch and its validation/cascade closure."""
    sequence = 0

    async def call_optional(
        label: str,
        action: object,
        arguments: dict[str, object],
        target_key: str,
        value_type: object,
    ) -> object | None:
        nonlocal sequence
        sequence += 1
        try:
            value = await execution.call(
                f"source-sparse-{sequence}-{label}",
                action,  # type: ignore[arg-type]
                arguments,
                target=execution.address_for(target_key),
            )
        except RuntimeRemoteFault:
            return None
        return decode_typed(value, value_type)

    def reference_uuid(value: object) -> UUID | None:
        resource_id = getattr(value, "resource_id", None)
        try:
            return resource_id if isinstance(resource_id, UUID) else UUID(str(resource_id))
        except TypeError, ValueError, AttributeError:
            return None

    def reference_text(value: object) -> str | None:
        resource_id = getattr(value, "resource_id", None)
        return str(resource_id) if resource_id is not None else None

    migrations: dict[str, RtgMigrationRecord] = {}
    migration_ids = {
        *(
            value
            for value in (
                reference_text(change.migration_ref)
                for change in change_batch.migration_changes.status_changes
            )
            if value is not None
        ),
        *(
            value
            for value in (
                reference_text(change.migration_ref)
                for change in change_batch.migration_changes.evidence_additions
            )
            if value is not None
        ),
        *(
            value
            for value in (
                reference_text(ref) for ref in change_batch.migration_changes.delete_migrations
            )
            if value is not None
        ),
    }
    for migration_id in sorted(migration_ids):
        value = await call_optional(
            "migration",
            RTG_MIGRATION_ACTIONS["get_migration"],
            {"migration_id": migration_id},
            migration_instance_key,
            RtgMigrationRecord,
        )
        if isinstance(value, RtgMigrationRecord) and value.migration_id is not None:
            migrations[value.migration_id] = value

    migration_candidates = (
        *migrations.values(),
        *(write.migration for write in change_batch.migration_changes.migration_writes),
    )
    schema_ids: set[UUID] = {
        value
        for value in (reference_uuid(ref) for ref in change_batch.schema_changes.delete_definitions)
        if value is not None
    }
    schema_ids.update(
        value
        for value in (
            reference_uuid(change.target_ref) for change in change_batch.schema_changes.set_live
        )
        if value is not None
    )
    constraint_ids: set[UUID] = {
        value
        for value in (
            reference_uuid(ref) for ref in change_batch.constraint_changes.delete_constraints
        )
        if value is not None
    }
    constraint_ids.update(
        value
        for value in (
            reference_uuid(change.target_ref) for change in change_batch.constraint_changes.set_live
        )
        if value is not None
    )
    graph_ids: set[UUID] = {
        value
        for value in (
            reference_uuid(ref)
            for refs in (
                change_batch.graph_changes.delete_anchors,
                change_batch.graph_changes.delete_data_objects,
                change_batch.graph_changes.delete_links,
            )
            for ref in refs
        )
        if value is not None
    }
    cascade_ids: set[UUID] = {
        value
        for value in (
            reference_uuid(ref)
            for refs in (
                change_batch.graph_changes.delete_anchors,
                change_batch.graph_changes.delete_data_objects,
            )
            for ref in refs
        )
        if value is not None
    }
    cascade_ids.update(
        value
        for value in (
            reference_uuid(change.data_ref) for change in change_batch.graph_changes.dissociate_data
        )
        if value is not None
    )
    data_anchor_lookup_ids: set[UUID] = {
        value
        for value in (reference_uuid(ref) for ref in change_batch.graph_changes.delete_data_objects)
        if value is not None
    }
    data_anchor_lookup_ids.update(
        value
        for value in (
            reference_uuid(change.object_ref) for change in change_batch.graph_changes.set_live
        )
        if value is not None
    )
    data_anchor_lookup_ids.update(
        value
        for value in (
            reference_uuid(change.data_ref)
            for change in (
                *change_batch.graph_changes.associate_data,
                *change_batch.graph_changes.dissociate_data,
            )
        )
        if value is not None
    )
    graph_ids.update(
        value
        for value in (
            reference_uuid(ref)
            for change in change_batch.graph_changes.set_live
            for ref in (change.object_ref,)
        )
        if value is not None
    )
    for write in change_batch.graph_changes.data_object_writes:
        graph_ids.update(
            value
            for value in (reference_uuid(ref) for ref in write.anchor_refs)
            if value is not None
        )
    for write in change_batch.graph_changes.link_writes:
        graph_ids.update(
            value
            for value in (
                reference_uuid(write.source_ref),
                reference_uuid(write.target_ref),
            )
            if value is not None
        )
    for change in (
        *change_batch.graph_changes.associate_data,
        *change_batch.graph_changes.dissociate_data,
    ):
        graph_ids.update(
            value
            for value in (
                reference_uuid(change.anchor_ref),
                reference_uuid(change.data_ref),
            )
            if value is not None
        )
    for migration in migration_candidates:
        schema_ids.update((*migration.schema_make_live, *migration.schema_make_non_live))
        constraint_ids.update(
            (*migration.constraint_make_live, *migration.constraint_make_non_live)
        )
        graph_ids.update((*migration.graph_make_live, *migration.graph_make_non_live))

    schema_values: dict[UUID, RtgSchemaDefinition] = {}
    for definition_uuid in sorted(schema_ids, key=str):
        value = await call_optional(
            "schema",
            RTG_SCHEMA_ACTIONS["get_definition"],
            {"definition_uuid": definition_uuid},
            schema_instance_key,
            RtgSchemaDefinition,
        )
        if isinstance(value, RtgSchemaDefinition) and value.uuid is not None:
            schema_values[value.uuid] = value

    constraint_values: dict[UUID, RtgConstraintDefinition] = {}
    for constraint_uuid in sorted(constraint_ids, key=str):
        value = await call_optional(
            "constraint",
            RTG_CONSTRAINTS_ACTIONS["get_constraint"],
            {"constraint_uuid": constraint_uuid},
            constraints_instance_key,
            RtgConstraintDefinition,
        )
        if isinstance(value, RtgConstraintDefinition) and value.uuid is not None:
            constraint_values[value.uuid] = value

    graph_values: dict[UUID, RtgObject] = {}
    for object_uuid in sorted(graph_ids, key=str):
        value = await call_optional(
            "graph",
            RTG_GRAPH_ACTIONS["get_object"],
            {"object_uuid": object_uuid},
            graph_instance_key,
            RtgObject,
        )
        if isinstance(value, (RtgAnchor, RtgDataObject, RtgLink)) and value.uuid is not None:
            graph_values[value.uuid] = value

    type_keys = {
        *(write.type for write in change_batch.graph_changes.anchor_writes),
        *(write.type for write in change_batch.graph_changes.data_object_writes),
        *(write.type for write in change_batch.graph_changes.link_writes),
        *(write.definition.type_key for write in change_batch.schema_changes.definition_writes),
        *(value.type_key for value in schema_values.values()),
        *(value.type for value in graph_values.values()),
        *(
            target
            for write in change_batch.constraint_changes.constraint_writes
            for target in write.constraint.target_type_keys
        ),
        *(target for value in constraint_values.values() for target in value.target_type_keys),
    }
    for type_key in sorted(type_keys):
        definitions = await call_optional(
            "schema-type",
            RTG_SCHEMA_ACTIONS["list_definitions_by_type_key"],
            {
                "schema_type_key": type_key,
                "kind": None,
                "live": None,
                "offset": 0,
                "limit": 200,
            },
            schema_instance_key,
            RtgSchemaDefinitionList,
        )
        if isinstance(definitions, RtgSchemaDefinitionList):
            schema_values.update(
                (item.uuid, item) for item in definitions.definitions if item.uuid is not None
            )
        constraints = await call_optional(
            "constraint-target",
            RTG_CONSTRAINTS_ACTIONS["list_constraints_by_target"],
            {"target_type_key": type_key, "kind": None, "live": None},
            constraints_instance_key,
            RtgConstraintDefinitionList,
        )
        if isinstance(constraints, RtgConstraintDefinitionList):
            constraint_values.update(
                (item.uuid, item) for item in constraints.constraints if item.uuid is not None
            )
        offset = 0
        while True:
            objects = await call_optional(
                "graph-type",
                RTG_GRAPH_ACTIONS["list_by_type"],
                {"object_type": type_key, "offset": offset, "limit": 200},
                graph_instance_key,
                RtgObjectList,
            )
            if not isinstance(objects, RtgObjectList):
                break
            graph_values.update(
                (item.uuid, item) for item in objects.objects if item.uuid is not None
            )
            if len(objects.objects) < 200:
                break
            offset += len(objects.objects)

    anchor_data: dict[UUID, set[UUID]] = {}
    inspected: set[UUID] = set()
    while pending := sorted(set(graph_values).difference(inspected), key=str):
        for object_uuid in pending:
            inspected.add(object_uuid)
            item = graph_values[object_uuid]
            if object_uuid in cascade_ids:
                links = await call_optional(
                    "incident-links",
                    RTG_GRAPH_ACTIONS["list_incident_links"],
                    {
                        "object_uuid": object_uuid,
                        "direction": "both",
                        "offset": 0,
                        "limit": 200,
                    },
                    graph_instance_key,
                    RtgLinkList,
                )
                if isinstance(links, RtgLinkList):
                    graph_values.update(
                        (link.uuid, link) for link in links.links if link.uuid is not None
                    )
                    for link in links.links:
                        graph_ids.update((link.source_uuid, link.target_uuid))
            if isinstance(item, RtgAnchor):
                data = await call_optional(
                    "anchor-data",
                    RTG_GRAPH_ACTIONS["list_anchor_data"],
                    {"anchor_uuid": object_uuid, "offset": 0, "limit": 200},
                    graph_instance_key,
                    RtgDataObjectList,
                )
                if isinstance(data, RtgDataObjectList):
                    anchor_data.setdefault(object_uuid, set()).update(
                        value.uuid for value in data.data_objects if value.uuid is not None
                    )
                    graph_values.update(
                        (value.uuid, value) for value in data.data_objects if value.uuid is not None
                    )
            elif isinstance(item, RtgDataObject) and object_uuid in data_anchor_lookup_ids:
                anchors = await call_optional(
                    "data-anchors",
                    RTG_GRAPH_ACTIONS["list_data_anchors"],
                    {"data_uuid": object_uuid, "offset": 0, "limit": 200},
                    graph_instance_key,
                    RtgAnchorList,
                )
                if isinstance(anchors, RtgAnchorList):
                    for anchor in anchors.anchors:
                        if anchor.uuid is not None:
                            graph_values[anchor.uuid] = anchor
                            anchor_data.setdefault(anchor.uuid, set()).add(object_uuid)
            elif isinstance(item, RtgLink):
                graph_ids.update((item.source_uuid, item.target_uuid))
        missing_endpoints = sorted(graph_ids.difference(graph_values), key=str)
        for object_uuid in missing_endpoints:
            value = await call_optional(
                "graph-endpoint",
                RTG_GRAPH_ACTIONS["get_object"],
                {"object_uuid": object_uuid},
                graph_instance_key,
                RtgObject,
            )
            if isinstance(value, (RtgAnchor, RtgDataObject, RtgLink)) and value.uuid is not None:
                graph_values[value.uuid] = value

    support_type_keys = {value.type for value in graph_values.values()}.difference(type_keys)
    for type_key in sorted(support_type_keys):
        definitions = await call_optional(
            "schema-support-type",
            RTG_SCHEMA_ACTIONS["list_definitions_by_type_key"],
            {
                "schema_type_key": type_key,
                "kind": None,
                "live": None,
                "offset": 0,
                "limit": 200,
            },
            schema_instance_key,
            RtgSchemaDefinitionList,
        )
        if isinstance(definitions, RtgSchemaDefinitionList):
            schema_values.update(
                (item.uuid, item) for item in definitions.definitions if item.uuid is not None
            )

    return (
        ValidationGraphProjection(tuple(graph_values.values()), anchor_data),
        ValidationSchemaProjection(tuple(schema_values.values())),
        ValidationConstraintProjection(tuple(constraint_values.values())),
        ValidationMigrationProjection(tuple(migrations.values())),
    )


async def _coherent_sources(
    execution: ComponentExecution,
    *,
    graph_instance_key: str,
    schema_instance_key: str,
    constraints_instance_key: str,
    migration_instance_key: str,
    change_batch: RtgChangeBatch | None = None,
) -> tuple[
    ValidationGraphProjection,
    ValidationSchemaProjection,
    ValidationConstraintProjection,
    ValidationMigrationProjection,
]:
    """Build one invocation-local read view without snapshot state transfer."""
    if change_batch is not None:
        return await _sparse_batch_sources(
            execution,
            change_batch,
            graph_instance_key=graph_instance_key,
            schema_instance_key=schema_instance_key,
            constraints_instance_key=constraints_instance_key,
            migration_instance_key=migration_instance_key,
        )
    graph_target = execution.address_for(graph_instance_key)
    counts_value = await execution.call(
        "source-graph-types",
        RTG_GRAPH_ACTIONS["count_by_type"],
        {"kind": None, "live": None},
        target=graph_target,
    )
    type_keys = sorted({item.type for item in decode_typed(counts_value, RtgTypeCountList).counts})
    graph_objects: list[RtgObject] = []
    for type_index, type_key in enumerate(type_keys):
        offset = 0
        while True:
            value = await execution.call(
                f"source-graph-type-{type_index}-{offset}",
                RTG_GRAPH_ACTIONS["list_by_type"],
                {"object_type": type_key, "offset": offset, "limit": 200},
                target=graph_target,
            )
            page = decode_typed(value, RtgObjectList).objects
            graph_objects.extend(page)
            if len(page) < 200:
                break
            offset += len(page)
    anchor_data_index: dict[str, tuple[str, ...]] = {}
    for data_index, data_object in enumerate(
        item for item in graph_objects if isinstance(item, RtgDataObject)
    ):
        assert data_object.uuid is not None
        offset = 0
        anchors: list[RtgAnchor] = []
        while True:
            value = await execution.call(
                f"source-data-anchors-{data_index}-{offset}",
                RTG_GRAPH_ACTIONS["list_data_anchors"],
                {"data_uuid": str(data_object.uuid), "offset": offset, "limit": 200},
                target=graph_target,
            )
            page = decode_typed(value, RtgAnchorList).anchors
            anchors.extend(page)
            if len(page) < 200:
                break
            offset += len(page)
        for anchor in anchors:
            assert anchor.uuid is not None
            current = list(anchor_data_index.get(str(anchor.uuid), ()))
            current.append(str(data_object.uuid))
            anchor_data_index[str(anchor.uuid)] = tuple(sorted(current))
    graph_projection = ValidationGraphProjection(
        tuple(graph_objects),
        {
            UUID(anchor_uuid): {UUID(data_uuid) for data_uuid in data_uuids}
            for anchor_uuid, data_uuids in anchor_data_index.items()
        },
    )

    schema_definitions: list[RtgSchemaDefinition] = []
    offset = 0
    schema_target = execution.address_for(schema_instance_key)
    while True:
        value = await execution.call(
            f"source-schema-{offset}",
            RTG_SCHEMA_ACTIONS["list_definitions"],
            {"kind": None, "live": None, "offset": offset, "limit": 200},
            target=schema_target,
        )
        page = decode_typed(value, RtgSchemaDefinitionList).definitions
        schema_definitions.extend(page)
        if len(page) < 200:
            break
        offset += len(page)
    schema_projection = ValidationSchemaProjection(tuple(schema_definitions))

    constraint_definitions: list[RtgConstraintDefinition] = []
    offset = 0
    constraints_target = execution.address_for(constraints_instance_key)
    while True:
        value = await execution.call(
            f"source-constraints-{offset}",
            RTG_CONSTRAINTS_ACTIONS["list_constraints"],
            {"kind": None, "live": None, "offset": offset, "limit": 200},
            target=constraints_target,
        )
        page = decode_typed(value, RtgConstraintDefinitionList).constraints
        constraint_definitions.extend(page)
        if len(page) < 200:
            break
        offset += len(page)
    constraint_projection = ValidationConstraintProjection(tuple(constraint_definitions))

    migrations: list[RtgMigrationRecord] = []
    offset = 0
    migration_target = execution.address_for(migration_instance_key)
    while True:
        value = await execution.call(
            f"source-migration-{offset}",
            RTG_MIGRATION_ACTIONS["list_migrations"],
            {"status": None, "offset": offset, "limit": 200},
            target=migration_target,
        )
        page = decode_typed(value, RtgMigrationRecordList).migrations
        migrations.extend(page)
        if len(page) < 200:
            break
        offset += len(page)
    migration_projection = ValidationMigrationProjection(tuple(migrations))
    return (
        graph_projection,
        schema_projection,
        constraint_projection,
        migration_projection,
    )
