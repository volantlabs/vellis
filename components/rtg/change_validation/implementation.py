from __future__ import annotations

import dataclasses
from typing import Any, cast
from uuid import UUID

from components.rtg.change_validation.protocol import (
    RtgChangeBatch,
    RtgChangeReference,
    RtgChangeValidator,
    RtgConstraintChangeSet,
    RtgGraphAnchorWrite,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
    RtgGraphLinkWrite,
    RtgGraphLiveStatusChange,
    RtgLiveStatusChange,
    RtgSchemaChangeSet,
    RtgValidationFinding,
    RtgValidationInputInvalid,
    RtgValidationOptions,
    RtgValidationReport,
)
from components.rtg.constraints.protocol import (
    RtgConstraintCardinalityPayload,
    RtgConstraintDefinition,
    RtgConstraintQueryPatternPayload,
    RtgConstraints,
)
from components.rtg.diagnostics import rtg_diagnostic
from components.rtg.graph.protocol import (
    JsonObject,
    RtgAnchor,
    RtgDataObject,
    RtgGraph,
    RtgLink,
    RtgObject,
)
from components.rtg.migration.protocol import (
    RtgMigration,
    RtgMigrationCutoverPlan,
    RtgMigrationReplacement,
    RtgMigrationStatusTransitionInvalid,
)
from components.rtg.query.protocol import RtgQueryEngine, RtgQueryOptions, RtgQuerySpec
from components.rtg.schema.protocol import (
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgLinkSchemaPayload,
    RtgSchema,
    RtgSchemaDefinition,
    RtgSchemaDefinitionNotFound,
    RtgSchemaField,
)

_TRACKS = {"schema_object", "constraint_network", "migration_cutover"}
_SEVERITY_ORDER = {"blocking": 0, "warning": 1, "informational": 2}


class DeterministicRtgChangeValidator(RtgChangeValidator):
    """Deterministic, side-effect-free RTG change validator."""

    def validate_batch(
        self,
        graph: object,
        schema: object,
        constraints: object,
        migration: object | None,
        query: object,
        change_batch: RtgChangeBatch,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        _validate_references(change_batch)
        options = validation_options or RtgValidationOptions()
        tracks = _selected_tracks(options)
        findings: list[RtgValidationFinding] = []
        pre_projection_findings: list[RtgValidationFinding] = []
        if "schema_object" in tracks:
            pre_projection_findings.extend(_validate_graph_reference_closure(graph, change_batch))
        if pre_projection_findings:
            pre_projection_findings.extend(_validate_graph_writes(schema, change_batch))
            return _report(pre_projection_findings, options)
        try:
            projected_graph, projected_schema, projected_constraints, projected_migration = (
                _project_batch(graph, schema, constraints, migration, change_batch)
            )
        except Exception as error:
            projected_findings: list[RtgValidationFinding] = []
            if "schema_object" in tracks:
                projected_findings.extend(_validate_graph_writes(schema, change_batch))
            projected_findings.append(
                _finding(
                    "schema_object",
                    "schema_object.projection_failed",
                    str(error),
                )
            )
            return _report(
                projected_findings,
                options,
            )
        post_state_findings: list[RtgValidationFinding] = []
        if "schema_object" in tracks:
            post_state_findings.extend(_validate_current_graph(projected_graph, projected_schema))
        if "constraint_network" in tracks:
            post_state_findings.extend(
                _validate_constraints(
                    projected_graph,
                    projected_schema,
                    projected_constraints,
                    query,
                )
            )
        findings.extend(post_state_findings)
        if "migration_cutover" in tracks and migration is not None:
            if _has_cutover_projection(change_batch):
                findings.extend(
                    _validate_live_status_changes_current_state(
                        graph,
                        schema,
                        constraints,
                        change_batch,
                    )
                )
                if _has_blocking(post_state_findings):
                    findings.append(
                        _finding(
                            "migration_cutover",
                            "migration_cutover.post_state_invalid",
                            "projected cutover state",
                        )
                    )
            findings.extend(
                _validate_migration_batch(
                    migration,
                    change_batch,
                    projected_graph,
                    projected_schema,
                    projected_constraints,
                )
            )
            findings.extend(
                _validate_staged_migration_cutover_projections(
                    projected_graph,
                    projected_schema,
                    projected_constraints,
                    projected_migration,
                    query,
                    change_batch,
                    tracks,
                )
            )
        return _report(findings, options)

    def validate_graph_state(
        self,
        graph: object,
        schema: object,
        constraints: object,
        migration: object | None,
        query: object,
        migration_ids: tuple[str, ...] | None = None,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        options = validation_options or RtgValidationOptions()
        tracks = _selected_tracks(options)
        findings: list[RtgValidationFinding] = []
        if migration_ids and migration is not None:
            migration_findings, projected = _project_migration_ids(
                graph,
                schema,
                constraints,
                migration,
                migration_ids,
            )
            if "migration_cutover" in tracks:
                findings.extend(migration_findings)
            if projected is not None:
                projected_graph, projected_schema, projected_constraints, _projected_migration = (
                    projected
                )
                post_state_findings: list[RtgValidationFinding] = []
                if "schema_object" in tracks:
                    post_state_findings.extend(
                        _validate_current_graph(projected_graph, projected_schema)
                    )
                if "constraint_network" in tracks:
                    post_state_findings.extend(
                        _validate_constraints(
                            projected_graph,
                            projected_schema,
                            projected_constraints,
                            query,
                        )
                    )
                findings.extend(post_state_findings)
                if "migration_cutover" in tracks and _has_blocking(post_state_findings):
                    findings.append(
                        _finding(
                            "migration_cutover",
                            "migration_cutover.post_state_invalid",
                            ",".join(migration_ids),
                        )
                    )
            return _report(findings, options)
        if "schema_object" in tracks:
            findings.extend(_validate_current_graph(graph, schema))
        if "constraint_network" in tracks:
            findings.extend(_validate_constraints(graph, schema, constraints, query))
        if "migration_cutover" in tracks and migration_ids and migration is not None:
            findings.extend(_validate_migration_ids(migration, migration_ids))
        return _report(findings, options)


def _project_batch(
    graph: object,
    schema: object,
    constraints: object,
    migration: object | None,
    change_batch: RtgChangeBatch,
) -> tuple[RtgGraph, RtgSchema, RtgConstraints, RtgMigration | None]:
    _require_graph(graph)
    _require_schema(schema)
    _require_constraints(constraints)
    graph_type = cast(Any, type(graph))
    schema_type = cast(Any, type(schema))
    constraints_type = cast(Any, type(constraints))
    graph_view = cast(
        RtgGraph,
        graph_type.import_snapshot(cast(RtgGraph, graph).export_snapshot()),
    )
    schema_view = cast(
        RtgSchema,
        schema_type.import_snapshot(cast(RtgSchema, schema).export_snapshot()),
    )
    constraints_view = cast(
        RtgConstraints,
        constraints_type.import_snapshot(cast(RtgConstraints, constraints).export_snapshot()),
    )
    migration_view = (
        cast(
            RtgMigration,
            cast(Any, type(migration)).import_snapshot(
                cast(RtgMigration, migration).export_snapshot()
            ),
        )
        if migration is not None
        else None
    )

    for write in change_batch.graph_changes.anchor_writes:
        graph_view.put_anchor(
            RtgAnchor(
                uuid=_uuid_or_raise(write.ref),
                type=write.type,
                display_name=write.display_name,
                system=write.system,
            )
        )
    for write in change_batch.graph_changes.data_object_writes:
        graph_view.put_data_object(
            RtgDataObject(
                uuid=_uuid_or_raise(write.ref),
                type=write.type,
                properties=write.properties,
                system=write.system,
            ),
            tuple(_uuid_or_raise(ref) for ref in write.anchor_refs),
        )
    for write in change_batch.graph_changes.link_writes:
        graph_view.put_link(
            RtgLink(
                uuid=_uuid_or_raise(write.ref),
                type=write.type,
                source_uuid=_uuid_or_raise(write.source_ref),
                target_uuid=_uuid_or_raise(write.target_ref),
                system=write.system,
            )
        )
    for change in change_batch.graph_changes.associate_data:
        graph_view.associate_data(
            _uuid_or_raise(change.anchor_ref), _uuid_or_raise(change.data_ref)
        )
    for change in change_batch.graph_changes.dissociate_data:
        graph_view.dissociate_data(
            _uuid_or_raise(change.anchor_ref), _uuid_or_raise(change.data_ref)
        )
    for ref in change_batch.graph_changes.delete_links:
        graph_view.delete_link(_uuid_or_raise(ref))
    for ref in change_batch.graph_changes.delete_data_objects:
        graph_view.delete_data_object(_uuid_or_raise(ref))
    for ref in change_batch.graph_changes.delete_anchors:
        graph_view.delete_anchor(_uuid_or_raise(ref))
    for change in change_batch.graph_changes.set_live:
        _put_graph_with_live(graph_view, _uuid_or_raise(change.object_ref), change.live)

    for write in change_batch.schema_changes.definition_writes:
        schema_view.put_definition(write.definition)
    for ref in change_batch.schema_changes.delete_definitions:
        schema_view.delete_definition(_uuid_or_raise(ref))
    for change in change_batch.schema_changes.set_live:
        definition = schema_view.get_definition(_uuid_or_raise(change.target_ref))
        schema_view.put_definition(
            dataclasses.replace(definition, system={**definition.system, "live": change.live})
        )

    for write in change_batch.constraint_changes.constraint_writes:
        constraints_view.put_constraint(write.constraint)
    for ref in change_batch.constraint_changes.delete_constraints:
        constraints_view.delete_constraint(_uuid_or_raise(ref))
    for change in change_batch.constraint_changes.set_live:
        constraint = constraints_view.get_constraint(_uuid_or_raise(change.target_ref))
        constraints_view.put_constraint(
            dataclasses.replace(constraint, system={**constraint.system, "live": change.live})
        )

    if migration_view is not None:
        for write in change_batch.migration_changes.migration_writes:
            migration_view.put_migration(write.migration)
        for change in change_batch.migration_changes.status_changes:
            migration_view.set_status(
                _reference_text(change.migration_ref),
                change.status,
                change.status_metadata,
            )
        for change in change_batch.migration_changes.evidence_additions:
            migration_view.add_evidence(_reference_text(change.migration_ref), change.evidence)
        for ref in change_batch.migration_changes.delete_migrations:
            migration_view.delete_migration(_reference_text(ref))

    return graph_view, schema_view, constraints_view, migration_view


def _project_migration_ids(
    graph: object,
    schema: object,
    constraints: object,
    migration: object,
    migration_ids: tuple[str, ...],
) -> tuple[
    list[RtgValidationFinding],
    tuple[RtgGraph, RtgSchema, RtgConstraints, RtgMigration | None] | None,
]:
    _require_migration(migration)
    migration = cast(RtgMigration, migration)
    findings: list[RtgValidationFinding] = []
    plans: list[RtgMigrationCutoverPlan] = []
    for migration_id in migration_ids:
        try:
            plans.append(
                RtgMigrationCutoverPlan.from_migration(migration.get_migration(migration_id))
            )
        except Exception:
            findings.append(
                _finding("migration_cutover", "migration_cutover.reference_missing", migration_id)
            )
    if findings:
        return findings, None
    state_findings = _validate_migration_plans_against_state(
        graph,
        schema,
        constraints,
        tuple(plans),
    )
    findings.extend(state_findings)
    if _has_blocking(state_findings):
        return findings, None

    try:
        projected = _project_batch(
            graph,
            schema,
            constraints,
            migration,
            _change_batch_from_cutover_plans(tuple(plans)),
        )
    except Exception as error:
        findings.append(
            _finding("migration_cutover", "migration_cutover.reference_missing", str(error))
        )
        return findings, None
    return findings, projected


def _change_batch_from_cutover_plans(
    plans: tuple[RtgMigrationCutoverPlan, ...],
) -> RtgChangeBatch:
    return RtgChangeBatch(
        graph_changes=RtgGraphChangeSet(
            set_live=tuple(
                RtgGraphLiveStatusChange(
                    object_ref=RtgChangeReference(resource_id=uuid_value),
                    live=live,
                )
                for plan in plans
                for uuid_value, live in (
                    *((uuid_value, False) for uuid_value in plan.graph_make_non_live),
                    *((uuid_value, True) for uuid_value in plan.graph_make_live),
                )
            )
        ),
        schema_changes=RtgSchemaChangeSet(
            set_live=tuple(
                RtgLiveStatusChange(
                    target_ref=RtgChangeReference(resource_id=uuid_value),
                    live=live,
                )
                for plan in plans
                for uuid_value, live in (
                    *((uuid_value, False) for uuid_value in plan.schema_make_non_live),
                    *((uuid_value, True) for uuid_value in plan.schema_make_live),
                )
            )
        ),
        constraint_changes=RtgConstraintChangeSet(
            set_live=tuple(
                RtgLiveStatusChange(
                    target_ref=RtgChangeReference(resource_id=uuid_value),
                    live=live,
                )
                for plan in plans
                for uuid_value, live in (
                    *((uuid_value, False) for uuid_value in plan.constraint_make_non_live),
                    *((uuid_value, True) for uuid_value in plan.constraint_make_live),
                )
            )
        ),
    )


def _put_graph_with_live(graph: RtgGraph, object_uuid: UUID, live: bool) -> None:
    obj = graph.get_object(object_uuid)
    system = {**obj.system, "live": live}
    if isinstance(obj, RtgAnchor):
        graph.put_anchor(dataclasses.replace(obj, system=system))
    elif isinstance(obj, RtgDataObject):
        anchors = tuple(
            anchor.uuid for anchor in graph.list_data_anchors(object_uuid).anchors if anchor.uuid
        )
        graph.put_data_object(dataclasses.replace(obj, system=system), anchors)
    else:
        graph.put_link(dataclasses.replace(obj, system=system))


def _validate_current_graph(graph: object, schema: object) -> list[RtgValidationFinding]:
    _require_graph(graph)
    _require_schema(schema)
    findings: list[RtgValidationFinding] = []
    graph = cast(RtgGraph, graph)
    schema = cast(RtgSchema, schema)
    for count in graph.count_by_type(live=True).counts:
        definitions = schema.list_definitions_by_type_key(count.type, live=True).definitions
        if not definitions:
            findings.append(_unknown_type_finding(count.type, kind="graph_object"))
            continue
        definition = definitions[0]
        for obj in graph.list_by_type(count.type).objects:
            if obj.system.get("live", True) is not True:
                continue
            findings.extend(_validate_object(obj, definition, graph))
    return findings


def _validate_graph_writes(
    schema: object, change_batch: RtgChangeBatch
) -> list[RtgValidationFinding]:
    _require_schema(schema)
    schema = cast(RtgSchema, schema)
    findings: list[RtgValidationFinding] = []
    for write in change_batch.graph_changes.anchor_writes:
        findings.extend(_validate_anchor_write(schema, write))
    for write in change_batch.graph_changes.data_object_writes:
        findings.extend(_validate_data_write(schema, write))
    for write in change_batch.graph_changes.link_writes:
        findings.extend(_validate_link_write(schema, write))
    return findings


def _validate_graph_reference_closure(
    graph: object,
    change_batch: RtgChangeBatch,
) -> list[RtgValidationFinding]:
    _require_graph(graph)
    graph = cast(RtgGraph, graph)
    proposed_anchors = {
        _uuid_or_raise(write.ref) for write in change_batch.graph_changes.anchor_writes
    }
    proposed_data = {
        _uuid_or_raise(write.ref) for write in change_batch.graph_changes.data_object_writes
    }
    findings: list[RtgValidationFinding] = []

    def anchor_exists(ref: RtgChangeReference) -> bool:
        uuid_value = _uuid_or_raise(ref)
        if uuid_value in proposed_anchors:
            return True
        try:
            return isinstance(graph.get_object(uuid_value), RtgAnchor)
        except Exception:
            return False

    def data_exists(ref: RtgChangeReference) -> bool:
        uuid_value = _uuid_or_raise(ref)
        if uuid_value in proposed_data:
            return True
        try:
            return isinstance(graph.get_object(uuid_value), RtgDataObject)
        except Exception:
            return False

    for write_index, write in enumerate(change_batch.graph_changes.data_object_writes):
        for ref_index, ref in enumerate(write.anchor_refs):
            if not anchor_exists(ref):
                findings.append(
                    _graph_reference_missing(
                        f"graph_changes.data_object_writes[{write_index}].anchor_refs[{ref_index}]",
                        ref,
                        "anchor",
                    )
                )
    for index, write in enumerate(change_batch.graph_changes.link_writes):
        if not anchor_exists(write.source_ref):
            findings.append(
                _graph_reference_missing(
                    f"graph_changes.link_writes[{index}].source_ref",
                    write.source_ref,
                    "anchor",
                )
            )
        if not anchor_exists(write.target_ref):
            findings.append(
                _graph_reference_missing(
                    f"graph_changes.link_writes[{index}].target_ref",
                    write.target_ref,
                    "anchor",
                )
            )
    for index, change in enumerate(change_batch.graph_changes.associate_data):
        if not anchor_exists(change.anchor_ref):
            findings.append(
                _graph_reference_missing(
                    f"graph_changes.associate_data[{index}].anchor_ref",
                    change.anchor_ref,
                    "anchor",
                )
            )
        if not data_exists(change.data_ref):
            findings.append(
                _graph_reference_missing(
                    f"graph_changes.associate_data[{index}].data_ref",
                    change.data_ref,
                    "data_object",
                )
            )
    return findings


def _graph_reference_missing(
    path: str,
    ref: RtgChangeReference,
    expected_kind: str,
) -> RtgValidationFinding:
    affected = (
        f"{path}.resource_id={_reference_text(ref)} does not resolve to a live or "
        f"same-request {expected_kind}"
    )
    return _finding(
        "schema_object",
        "schema_object.reference_missing",
        affected,
        suggestion=(
            "Resolve existing objects with rtg_execute_query; call rtg_get_usage_guide "
            "with topic='lookup_examples' for copy-pastable lookup queries."
        ),
        diagnostic=rtg_diagnostic(
            code="schema_object.reference_missing",
            category="reference_resolution",
            path=path,
            problem=f"The reference does not resolve to a live or same-request {expected_kind}.",
            remedy=(
                "Resolve existing object UUIDs with rtg_execute_query or "
                "rtg_resolve_anchor_by_fact, or use local_ref only for objects created in the "
                "same request."
            ),
            minimal_example={
                "ref": {"resource_id": "11111111-1111-1111-1111-111111111111"}
            },
            guide_topics=("workflow_patterns", "lookup_examples", "live_write"),
        ),
    )


def _unknown_type_finding(type_key: str, *, kind: str = "object") -> RtgValidationFinding:
    return _finding(
        "schema_object",
        "schema_object.unknown_type",
        type_key,
        suggestion=(
            "Discover live schema with rtg_discover_anchor_types or rtg_get_schema_pack. "
            "If this is a new type, stage and cut over schema before writing graph data."
        ),
        diagnostic=rtg_diagnostic(
            code="schema_object.unknown_type",
            category="schema_contract",
            path=f"{kind}.type",
            problem=f"No live schema definition exists for type {type_key!r}.",
            remedy=(
                "Use an existing live type key, or stage and cut over a schema definition for this "
                "type before writing graph data."
            ),
            guide_topics=("workflow_patterns", "schema_staging_minimal", "live_write"),
        ),
    )


def _validate_anchor_write(
    schema: RtgSchema, write: RtgGraphAnchorWrite
) -> list[RtgValidationFinding]:
    try:
        schema.list_definitions_by_type_key(write.type, kind="anchor", live=True).definitions[0]
    except IndexError, RtgSchemaDefinitionNotFound:
        return [_unknown_type_finding(write.type, kind="anchor_write")]
    return []


def _validate_data_write(
    schema: RtgSchema, write: RtgGraphDataObjectWrite
) -> list[RtgValidationFinding]:
    try:
        definition = schema.list_definitions_by_type_key(
            write.type, kind="data_object", live=True
        ).definitions[0]
    except IndexError, RtgSchemaDefinitionNotFound:
        return [_unknown_type_finding(write.type, kind="data_object_write")]
    data = RtgDataObject(uuid=_uuid_or_nil(write.ref), type=write.type, properties=write.properties)
    return _validate_data_object(data, definition)


def _validate_link_write(schema: RtgSchema, write: RtgGraphLinkWrite) -> list[RtgValidationFinding]:
    try:
        schema.list_definitions_by_type_key(write.type, kind="link", live=True).definitions[0]
    except IndexError, RtgSchemaDefinitionNotFound:
        return [_unknown_type_finding(write.type, kind="link_write")]
    return []


def _validate_object(
    obj: RtgObject,
    definition: RtgSchemaDefinition,
    graph: RtgGraph,
) -> list[RtgValidationFinding]:
    if isinstance(obj, RtgAnchor):
        return _validate_anchor(obj, definition, graph)
    if isinstance(obj, RtgDataObject):
        return _validate_data_object(obj, definition)
    return _validate_link(obj, definition, graph)


def _validate_anchor(
    anchor: RtgAnchor,
    definition: RtgSchemaDefinition,
    graph: RtgGraph,
) -> list[RtgValidationFinding]:
    if not isinstance(definition.payload, RtgAnchorSchemaPayload):
        return [_unknown_type_finding(anchor.type, kind="anchor")]
    findings: list[RtgValidationFinding] = []
    anchor_uuid = _concrete_uuid(anchor.uuid)
    associated_types = {item.type for item in graph.list_anchor_data(anchor_uuid).data_objects}
    for required_type in definition.payload.required_data_types:
        if required_type not in associated_types:
            affected = f"{anchor_uuid}:{required_type}"
            findings.append(
                _finding(
                    "schema_object",
                    "schema_object.missing_required_associated_data",
                    affected,
                    suggestion=(
                        "Write the required associated data object and associate it with the "
                        "anchor in the same request, or use rtg_apply_live_anchor_records."
                    ),
                    diagnostic=rtg_diagnostic(
                        code="schema_object.missing_required_associated_data",
                        category="validation_failure",
                        path="graph_changes.data_object_writes",
                        problem=(
                            f"Anchor {anchor_uuid} is missing required data type "
                            f"{required_type}."
                        ),
                        remedy=(
                            "Add a data object of the required type and link it to the anchor with "
                            "anchor_refs, or use the anchor-record facade."
                        ),
                        minimal_example={
                            "anchor_records": [
                                {
                                    "ref": {"local_ref": "item-alpha"},
                                    "type": "Item",
                                    "facts": [
                                        {"type": "ItemFacts", "properties": {"title": "Item alpha"}}
                                    ],
                                }
                            ]
                        },
                        guide_topics=("workflow_patterns", "live_write", "tool_call_shapes"),
                    ),
                )
            )
    return findings


def _validate_data_object(
    data_object: RtgDataObject,
    definition: RtgSchemaDefinition,
) -> list[RtgValidationFinding]:
    if not isinstance(definition.payload, RtgDataObjectSchemaPayload):
        return [_unknown_type_finding(data_object.type, kind="data_object")]
    findings: list[RtgValidationFinding] = []
    fields = definition.payload.properties
    for key in sorted(data_object.properties):
        if key not in fields:
            findings.append(
                _finding(
                    "schema_object",
                    "schema_object.undeclared_property",
                    f"{data_object.type}.{key}",
                )
            )
    for key, field in sorted(fields.items()):
        if field.required and key not in data_object.properties:
            affected = f"{data_object.type}.{key}"
            findings.append(
                _finding(
                    "schema_object",
                    "schema_object.missing_required_property",
                    affected,
                    suggestion=f"Add required property {key!r} to {data_object.type}.",
                    diagnostic=rtg_diagnostic(
                        code="schema_object.missing_required_property",
                        category="validation_failure",
                        path=f"{data_object.type}.properties.{key}",
                        problem=f"{data_object.type} requires property {key!r}.",
                        remedy="Add the missing property with a value allowed by the schema field.",
                        guide_topics=("workflow_patterns", "live_write", "schema_staging_minimal"),
                    ),
                )
            )
        elif key in data_object.properties and not _value_matches_field(
            data_object.properties[key], field
        ):
            affected = f"{data_object.type}.{key}"
            findings.append(
                _finding(
                    "schema_object",
                    "schema_object.property_kind_mismatch",
                    affected,
                    suggestion=(
                        f"Change {data_object.type}.{key} to one of the schema's allowed value "
                        "kinds."
                    ),
                    diagnostic=rtg_diagnostic(
                        code="schema_object.property_kind_mismatch",
                        category="validation_failure",
                        path=f"{data_object.type}.properties.{key}",
                        problem=(
                            f"{data_object.type}.{key} has a value kind that is not allowed by "
                            "the live schema."
                        ),
                        remedy=(
                            "Replace the value with one of the value kinds allowed by the schema."
                        ),
                        guide_topics=("workflow_patterns", "live_write", "schema_staging_minimal"),
                    ),
                )
            )
    return findings


def _validate_link(
    link: RtgLink,
    definition: RtgSchemaDefinition,
    graph: RtgGraph,
) -> list[RtgValidationFinding]:
    if not isinstance(definition.payload, RtgLinkSchemaPayload):
        return [_unknown_type_finding(link.type, kind="link")]
    source = graph.get_object(link.source_uuid)
    target = graph.get_object(link.target_uuid)
    if source.type not in definition.payload.allowed_source_types:
        return [
            _finding(
                "schema_object",
                "schema_object.link_endpoint_type_invalid",
                link.type,
                suggestion=(
                    "Use a source anchor type in "
                    f"{sorted(definition.payload.allowed_source_types)} for link type {link.type}."
                ),
                diagnostic=rtg_diagnostic(
                    code="schema_object.link_endpoint_type_invalid",
                    category="validation_failure",
                    path="graph_changes.link_writes.source_ref",
                    problem=(
                        f"Link type {link.type!r} does not allow source type {source.type!r}."
                    ),
                    remedy=(
                        "Resolve or create a source anchor whose type is allowed by the link "
                        "schema."
                    ),
                    accepted_fields=tuple(sorted(definition.payload.allowed_source_types)),
                    guide_topics=("workflow_patterns", "lookup_examples", "live_write"),
                ),
            )
        ]
    if target.type not in definition.payload.allowed_target_types:
        return [
            _finding(
                "schema_object",
                "schema_object.link_endpoint_type_invalid",
                link.type,
                suggestion=(
                    "Use a target anchor type in "
                    f"{sorted(definition.payload.allowed_target_types)} for link type {link.type}."
                ),
                diagnostic=rtg_diagnostic(
                    code="schema_object.link_endpoint_type_invalid",
                    category="validation_failure",
                    path="graph_changes.link_writes.target_ref",
                    problem=(
                        f"Link type {link.type!r} does not allow target type {target.type!r}."
                    ),
                    remedy=(
                        "Resolve or create a target anchor whose type is allowed by the link "
                        "schema."
                    ),
                    accepted_fields=tuple(sorted(definition.payload.allowed_target_types)),
                    guide_topics=("workflow_patterns", "lookup_examples", "live_write"),
                ),
            )
        ]
    return []


def _validate_constraints(
    graph: object,
    schema: object,
    constraints: object,
    query: object,
) -> list[RtgValidationFinding]:
    _require_graph(graph)
    _require_schema(schema)
    _require_constraints(constraints)
    _require_query(query)
    graph = cast(RtgGraph, graph)
    schema = cast(RtgSchema, schema)
    constraints = cast(RtgConstraints, constraints)
    query = cast(RtgQueryEngine, query)
    findings: list[RtgValidationFinding] = []
    live_type_keys = {item.type_key for item in schema.list_definitions(live=True).definitions}
    for constraint in constraints.list_constraints(live=True).constraints:
        unknown_targets = set(constraint.target_type_keys) - live_type_keys
        if unknown_targets:
            findings.append(
                _finding(
                    "constraint_network",
                    "constraint_network.constraint_target_unknown",
                    ",".join(sorted(unknown_targets)),
                )
            )
            continue
        payload = constraint.payload
        if isinstance(payload, RtgConstraintQueryPatternPayload):
            result = query.execute(graph, _as_query_spec(payload.query_spec), RtgQueryOptions())
            if payload.expectation == "must_match_at_least_one" and not result.bindings:
                findings.append(
                    _finding(
                        "constraint_network",
                        "constraint_network.pattern_unsatisfied",
                        str(constraint.uuid),
                    )
                )
            if payload.expectation == "must_match_none" and result.bindings:
                findings.append(
                    _finding(
                        "constraint_network",
                        "constraint_network.pattern_unsatisfied",
                        str(constraint.uuid),
                    )
                )
        elif isinstance(payload, RtgConstraintCardinalityPayload):
            result = query.execute(graph, _as_query_spec(payload.query_spec), RtgQueryOptions())
            count = sum(
                1 for row in result.bindings if _binding_present(row, payload.counted_binding)
            )
            if (payload.minimum is not None and count < payload.minimum) or (
                payload.maximum is not None and count > payload.maximum
            ):
                findings.append(
                    _finding(
                        "constraint_network",
                        "constraint_network.cardinality_out_of_bounds",
                        str(constraint.uuid),
                    )
                )
    return findings


def _validate_migration_batch(
    migration: object,
    change_batch: RtgChangeBatch,
    graph: object,
    schema: object,
    constraints: object,
) -> list[RtgValidationFinding]:
    _require_migration(migration)
    migration = cast(RtgMigration, migration)
    findings: list[RtgValidationFinding] = []
    for status_change in change_batch.migration_changes.status_changes:
        migration_id = _reference_text(status_change.migration_ref)
        try:
            current = migration.get_migration(migration_id)
            shadow = type(migration).import_snapshot(migration.export_snapshot())
            shadow.set_status(_concrete_migration_id(current.migration_id), status_change.status)
        except RtgMigrationStatusTransitionInvalid:
            findings.append(
                _finding(
                    "migration_cutover",
                    "migration_cutover.invalid_status_transition",
                    migration_id,
                )
            )
        except Exception:
            findings.append(
                _finding("migration_cutover", "migration_cutover.reference_missing", migration_id)
            )
    plans: list[RtgMigrationCutoverPlan] = []
    for write in change_batch.migration_changes.migration_writes:
        migration_id = _reference_text(write.ref)
        try:
            plans.append(RtgMigrationCutoverPlan.from_migration(write.migration))
        except Exception:
            findings.append(
                _finding("migration_cutover", "migration_cutover.reference_missing", migration_id)
            )
    findings.extend(
        _validate_migration_plans_against_state(graph, schema, constraints, tuple(plans))
    )
    return findings


def _validate_staged_migration_cutover_projections(
    graph: object,
    schema: object,
    constraints: object,
    migration: object | None,
    query: object,
    change_batch: RtgChangeBatch,
    tracks: set[str],
) -> list[RtgValidationFinding]:
    if migration is None:
        return []
    migration_ids: list[str] = []
    for write in change_batch.migration_changes.migration_writes:
        try:
            plan = RtgMigrationCutoverPlan.from_migration(write.migration)
        except Exception:
            continue
        if (
            plan.schema_make_live
            or plan.schema_make_non_live
            or plan.constraint_make_live
            or plan.constraint_make_non_live
            or plan.graph_make_live
            or plan.graph_make_non_live
        ):
            migration_ids.append(plan.migration_id)
    if not migration_ids:
        return []

    projection_findings, projected = _project_migration_ids(
        graph,
        schema,
        constraints,
        migration,
        tuple(migration_ids),
    )
    if _has_blocking(projection_findings) or projected is None:
        return []

    projected_graph, projected_schema, projected_constraints, _projected_migration = projected
    post_state_findings: list[RtgValidationFinding] = []
    if "schema_object" in tracks:
        post_state_findings.extend(_validate_current_graph(projected_graph, projected_schema))
    if "constraint_network" in tracks:
        post_state_findings.extend(
            _validate_constraints(
                projected_graph,
                projected_schema,
                projected_constraints,
                query,
            )
        )
    findings = list(post_state_findings)
    if "migration_cutover" in tracks and _has_blocking(post_state_findings):
        findings.append(
            _finding(
                "migration_cutover",
                "migration_cutover.post_state_invalid",
                ",".join(migration_ids),
            )
        )
    return findings


def _validate_live_status_changes_current_state(
    graph: object,
    schema: object,
    constraints: object,
    change_batch: RtgChangeBatch,
) -> list[RtgValidationFinding]:
    findings: list[RtgValidationFinding] = []
    schema = cast(RtgSchema, schema)
    constraints = cast(RtgConstraints, constraints)
    graph = cast(RtgGraph, graph)
    for change in change_batch.schema_changes.set_live:
        findings.extend(
            _validate_live_status_reference(schema.get_definition, change.target_ref, change.live)
        )
    for change in change_batch.constraint_changes.set_live:
        findings.extend(
            _validate_live_status_reference(
                constraints.get_constraint, change.target_ref, change.live
            )
        )
    for change in change_batch.graph_changes.set_live:
        findings.extend(
            _validate_live_status_reference(graph.get_object, change.object_ref, change.live)
        )
    return findings


def _validate_migration_plans_against_state(
    graph: object,
    schema: object,
    constraints: object,
    plans: tuple[RtgMigrationCutoverPlan, ...],
) -> list[RtgValidationFinding]:
    findings: list[RtgValidationFinding] = []
    schema = cast(RtgSchema, schema)
    constraints = cast(RtgConstraints, constraints)
    graph = cast(RtgGraph, graph)
    for plan in plans:
        for uuid_value in plan.schema_make_live:
            findings.extend(_validate_live_status_uuid(schema.get_definition, uuid_value, True))
        for uuid_value in plan.schema_make_non_live:
            findings.extend(_validate_live_status_uuid(schema.get_definition, uuid_value, False))
        for uuid_value in plan.constraint_make_live:
            findings.extend(
                _validate_live_status_uuid(constraints.get_constraint, uuid_value, True)
            )
        for uuid_value in plan.constraint_make_non_live:
            findings.extend(
                _validate_live_status_uuid(constraints.get_constraint, uuid_value, False)
            )
        for uuid_value in plan.graph_make_live:
            findings.extend(_validate_live_status_uuid(graph.get_object, uuid_value, True))
        for uuid_value in plan.graph_make_non_live:
            findings.extend(_validate_live_status_uuid(graph.get_object, uuid_value, False))
        for replacement in plan.schema_replacements:
            findings.extend(_validate_replacement_pair(schema.get_definition, replacement))
        for replacement in plan.constraint_replacements:
            findings.extend(_validate_replacement_pair(constraints.get_constraint, replacement))
        for replacement in plan.graph_replacements:
            findings.extend(_validate_replacement_pair(graph.get_object, replacement))
    return findings


def _validate_live_status_reference(
    lookup: object,
    ref: RtgChangeReference,
    target_live: bool,
) -> list[RtgValidationFinding]:
    return _validate_live_status_uuid(cast(Any, lookup), _uuid_or_raise(ref), target_live)


def _validate_live_status_uuid(
    lookup: object,
    uuid_value: UUID,
    target_live: bool,
) -> list[RtgValidationFinding]:
    try:
        current = cast(Any, lookup)(uuid_value)
    except Exception:
        return [
            _finding("migration_cutover", "migration_cutover.reference_missing", str(uuid_value))
        ]
    if _record_live(current) is target_live:
        return [
            _finding("migration_cutover", "migration_cutover.wrong_live_state", str(uuid_value))
        ]
    return []


def _validate_replacement_pair(
    lookup: object,
    replacement: RtgMigrationReplacement,
) -> list[RtgValidationFinding]:
    old_resource_id = replacement.old_resource_id
    new_resource_id = replacement.new_resource_id
    findings: list[RtgValidationFinding] = []
    try:
        old_record = cast(Any, lookup)(old_resource_id)
    except Exception:
        findings.append(
            _finding(
                "migration_cutover",
                "migration_cutover.reference_missing",
                str(old_resource_id),
            )
        )
        old_record = None
    try:
        new_record = cast(Any, lookup)(new_resource_id)
    except Exception:
        findings.append(
            _finding(
                "migration_cutover",
                "migration_cutover.reference_missing",
                str(new_resource_id),
            )
        )
        new_record = None
    if old_record is None or new_record is None:
        return findings
    if _record_type_signature(old_record) != _record_type_signature(new_record):
        findings.append(
            _finding(
                "migration_cutover",
                "migration_cutover.replacement_type_mismatch",
                f"{old_resource_id}->{new_resource_id}",
            )
        )
    return findings


def _record_live(record: object) -> bool:
    system = getattr(record, "system", {})
    if isinstance(system, dict):
        return system.get("live", True) is True
    return True


def _record_type_signature(record: object) -> tuple[object, ...]:
    if isinstance(record, RtgSchemaDefinition):
        return ("schema", record.kind, record.type_key)
    if isinstance(record, RtgConstraintDefinition):
        return ("constraint", record.kind, record.target_type_keys)
    if isinstance(record, RtgAnchor):
        return ("graph", "anchor", record.type)
    if isinstance(record, RtgDataObject):
        return ("graph", "data_object", record.type)
    if isinstance(record, RtgLink):
        return ("graph", "link", record.type)
    return (type(record).__name__,)


def _has_cutover_projection(change_batch: RtgChangeBatch) -> bool:
    return bool(
        change_batch.schema_changes.set_live
        or change_batch.constraint_changes.set_live
        or change_batch.graph_changes.set_live
    )


def _has_blocking(findings: list[RtgValidationFinding]) -> bool:
    return any(finding.severity == "blocking" for finding in findings)


def _validate_migration_ids(
    migration: object,
    migration_ids: tuple[str, ...],
) -> list[RtgValidationFinding]:
    _require_migration(migration)
    migration = cast(RtgMigration, migration)
    findings: list[RtgValidationFinding] = []
    for migration_id in migration_ids:
        try:
            migration.get_migration(migration_id)
        except Exception:
            findings.append(
                _finding("migration_cutover", "migration_cutover.reference_missing", migration_id)
            )
    return findings


def _value_matches_field(value: object, field: RtgSchemaField) -> bool:
    value_kind = _json_kind(value)
    if value_kind not in field.value_kinds:
        return False
    if value_kind == "object":
        if not isinstance(value, dict):
            return False
        for key, nested in field.properties.items():
            if nested.required and key not in value:
                return False
            if key in value and not _value_matches_field(value[key], nested):
                return False
    if value_kind == "list" and field.items is not None:
        if not isinstance(value, list):
            return False
        return all(_value_matches_field(item, field.items) for item in value)
    return True


def _json_kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        try:
            UUID(value)
            return "uuid"
        except ValueError:
            return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "list"
    return "unknown"


def _selected_tracks(options: RtgValidationOptions) -> set[str]:
    if options.finding_limit is not None and options.finding_limit <= 0:
        raise RtgValidationInputInvalid("finding_limit must be positive")
    if options.tracks == "all":
        return set(_TRACKS)
    tracks = set(options.tracks)
    if not tracks or tracks - _TRACKS:
        raise RtgValidationInputInvalid("invalid validation track selection")
    return tracks


def _validate_references(change_batch: RtgChangeBatch) -> None:
    refs: list[RtgChangeReference] = []
    refs.extend(write.ref for write in change_batch.graph_changes.anchor_writes)
    refs.extend(write.ref for write in change_batch.graph_changes.data_object_writes)
    refs.extend(write.ref for write in change_batch.graph_changes.link_writes)
    refs.extend(
        ref for write in change_batch.graph_changes.data_object_writes for ref in write.anchor_refs
    )
    refs.extend(write.source_ref for write in change_batch.graph_changes.link_writes)
    refs.extend(write.target_ref for write in change_batch.graph_changes.link_writes)
    refs.extend(change.anchor_ref for change in change_batch.graph_changes.associate_data)
    refs.extend(change.data_ref for change in change_batch.graph_changes.associate_data)
    refs.extend(change.anchor_ref for change in change_batch.graph_changes.dissociate_data)
    refs.extend(change.data_ref for change in change_batch.graph_changes.dissociate_data)
    refs.extend(change_batch.graph_changes.delete_anchors)
    refs.extend(change_batch.graph_changes.delete_data_objects)
    refs.extend(change_batch.graph_changes.delete_links)
    refs.extend(change.object_ref for change in change_batch.graph_changes.set_live)
    refs.extend(write.ref for write in change_batch.schema_changes.definition_writes)
    refs.extend(change_batch.schema_changes.delete_definitions)
    refs.extend(change.target_ref for change in change_batch.schema_changes.set_live)
    refs.extend(write.ref for write in change_batch.constraint_changes.constraint_writes)
    refs.extend(change_batch.constraint_changes.delete_constraints)
    refs.extend(change.target_ref for change in change_batch.constraint_changes.set_live)
    refs.extend(write.ref for write in change_batch.migration_changes.migration_writes)
    refs.extend(change_batch.migration_changes.delete_migrations)
    refs.extend(change.migration_ref for change in change_batch.migration_changes.status_changes)
    refs.extend(
        change.migration_ref for change in change_batch.migration_changes.evidence_additions
    )
    for ref in refs:
        if (ref.resource_id is None) == (ref.local_ref is None):
            raise RtgValidationInputInvalid("each change reference needs exactly one identity")


def _report(
    findings: list[RtgValidationFinding],
    options: RtgValidationOptions,
) -> RtgValidationReport:
    ordered = sorted(
        findings,
        key=lambda item: (
            _SEVERITY_ORDER.get(item.severity, 3),
            item.track,
            item.code,
            item.affected_references,
        ),
    )
    accepted = not any(item.severity == "blocking" for item in ordered)
    total_finding_count = len(ordered)
    if options.finding_limit is not None:
        ordered = ordered[: options.finding_limit]
    return RtgValidationReport(
        accepted=accepted,
        findings=tuple(ordered),
        evidence={
            "finding_count": len(ordered),
            "total_finding_count": total_finding_count,
            "truncated": len(ordered) != total_finding_count,
        },
    )


def _finding(
    track: str,
    code: str,
    affected: str,
    *,
    suggestion: str = "Use controller discovery or schema packs to repair the proposed model.",
    diagnostic: JsonObject | None = None,
) -> RtgValidationFinding:
    return RtgValidationFinding(
        track=track,
        severity="blocking" if not code.endswith("replacement_type_mismatch") else "warning",
        code=code,
        message=f"{code}: {affected}",
        suggestion=suggestion,
        affected_references=(affected,),
        diagnostic=diagnostic or {},
    )


def _binding_present(row: object, name: str) -> bool:
    anchors = getattr(row, "anchors", {})
    links = getattr(row, "links", {})
    data_objects = getattr(row, "data_objects", {})
    return name in anchors or name in links or name in data_objects


def _as_query_spec(value: object) -> RtgQuerySpec:
    if not isinstance(value, RtgQuerySpec):
        raise RtgValidationInputInvalid("constraint query_spec is not an RtgQuerySpec")
    return value


def _require_graph(value: object) -> None:
    required = ("count_by_type", "list_by_type", "list_anchor_data", "get_object")
    if not all(hasattr(value, name) for name in required):
        raise RtgValidationInputInvalid("graph read view is missing required contracts")


def _require_schema(value: object) -> None:
    required = ("list_definitions", "list_definitions_by_type_key")
    if not all(hasattr(value, name) for name in required):
        raise RtgValidationInputInvalid("schema read view is missing required contracts")


def _require_constraints(value: object) -> None:
    if not hasattr(value, "list_constraints"):
        raise RtgValidationInputInvalid("constraints read view is missing required contracts")


def _require_migration(value: object) -> None:
    if not all(hasattr(value, name) for name in ("get_migration", "export_snapshot")):
        raise RtgValidationInputInvalid("migration read view is missing required contracts")


def _require_query(value: object) -> None:
    if not hasattr(value, "execute"):
        raise RtgValidationInputInvalid("query engine is missing execute")


def _concrete_uuid(value: UUID | None) -> UUID:
    if value is None:
        raise RtgValidationInputInvalid("graph object UUID is not concrete")
    return value


def _uuid_or_nil(ref: RtgChangeReference) -> UUID:
    if isinstance(ref.resource_id, UUID):
        return ref.resource_id
    return UUID(int=0)


def _uuid_or_raise(ref: RtgChangeReference) -> UUID:
    if isinstance(ref.resource_id, UUID):
        return ref.resource_id
    if isinstance(ref.resource_id, str):
        return UUID(ref.resource_id)
    raise RtgValidationInputInvalid("change reference is not resolved")


def _reference_text(ref: RtgChangeReference) -> str:
    if ref.resource_id is not None:
        return str(ref.resource_id)
    if ref.local_ref is not None:
        return ref.local_ref
    raise RtgValidationInputInvalid("reference has no identity")


def _concrete_migration_id(value: str | None) -> str:
    if value is None:
        raise RtgValidationInputInvalid("migration ID is not concrete")
    return value
