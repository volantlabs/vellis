from __future__ import annotations

import dataclasses
from typing import Any, cast
from uuid import UUID

from components.rtg.change_validation import (
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
from components.rtg.constraints import (
    RtgConstraintCardinalityPayload,
    RtgConstraintDefinition,
    RtgConstraintQueryPatternPayload,
    RtgConstraintSnapshot,
)
from components.rtg.controller import (
    RtgControllerCutoverOptions,
    RtgControllerDiscoveryOptions,
    RtgControllerReplayOptions,
    RtgControllerRestoreOptions,
    RtgControllerSchemaPackOptions,
    RtgControllerValidationOptions,
    RtgSystemSnapshot,
)
from components.rtg.diagnostics import rtg_diagnostic
from components.rtg.graph import JsonObject, JsonValue, RtgGraphSnapshot
from components.rtg.migration import (
    RtgMigrationEvidence,
    RtgMigrationRecord,
    RtgMigrationReplacement,
    RtgMigrationSnapshot,
)
from components.rtg.query import (
    RtgQueryAnchorBucket,
    RtgQueryDataRequirement,
    RtgQueryDiagnosticOptions,
    RtgQueryLinkRequirement,
    RtgQueryOptions,
    RtgQueryOrderBy,
    RtgQueryPropertyPredicate,
    RtgQueryReturnSpec,
    RtgQuerySpec,
)
from components.rtg.schema import (
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgLinkSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaField,
    RtgSchemaSnapshot,
)


class RtgMcpInputInvalid(ValueError):
    """An MCP payload cannot be decoded into public RTG dataclasses."""

    def __init__(self, message: str, *, diagnostic: JsonObject | None = None) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic or {}


def encode_json(value: object) -> JsonValue:
    if dataclasses.is_dataclass(value):
        data = dataclasses.asdict(cast(Any, value))
        return {key: encode_json(item) for key, item in data.items()}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): encode_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [encode_json(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def decode_graph_changes(value: object) -> RtgGraphChangeSet:
    data = _object(value, "graph_changes")
    _reject_unknown_keys(
        data,
        {
            "anchor_writes",
            "data_object_writes",
            "link_writes",
            "associate_data",
            "dissociate_data",
            "delete_anchors",
            "delete_data_objects",
            "delete_links",
            "set_live",
        },
        "graph_changes",
        {
            "anchors": "anchor_writes",
            "data_objects": "data_object_writes",
            "links": "link_writes",
            "live": "set_live",
        },
    )
    return RtgGraphChangeSet(
        anchor_writes=tuple(
            RtgGraphAnchorWrite(
                ref=_uuid_ref(
                    _required_value(item, "ref", "anchor_writes.ref"),
                    "anchor_writes.ref",
                ),
                type=_required_str(item, "type"),
                display_name=_optional_str(item.get("display_name")),
                system=_json_object(item.get("system", {}), "anchor_writes.system"),
            )
            for item in _checked_objects(
                data.get("anchor_writes", []),
                "graph_changes.anchor_writes",
                {"ref", "type", "display_name", "system"},
                {"name": "display_name", "anchor_type": "type", "type_key": "type"},
            )
        ),
        data_object_writes=tuple(
            RtgGraphDataObjectWrite(
                ref=_uuid_ref(
                    _required_value(item, "ref", "data_object_writes.ref"),
                    "data_object_writes.ref",
                ),
                type=_required_str(item, "type"),
                properties=_json_object(item.get("properties", {}), "properties"),
                system=_json_object(item.get("system", {}), "data_object_writes.system"),
                anchor_refs=tuple(
                    _uuid_ref(ref, "data_object_writes.anchor_refs")
                    for ref in _list(item.get("anchor_refs", []), "anchor_refs")
                ),
            )
            for item in _checked_objects(
                data.get("data_object_writes", []),
                "graph_changes.data_object_writes",
                {"ref", "type", "properties", "system", "anchor_refs"},
                {
                    "data_type": "type",
                    "data_type_key": "type",
                    "attrs": "properties",
                    "anchors": "anchor_refs",
                },
            )
        ),
        link_writes=tuple(
            RtgGraphLinkWrite(
                ref=_uuid_ref(_required_value(item, "ref", "link_writes.ref"), "link_writes.ref"),
                type=_required_str(item, "type"),
                source_ref=_uuid_ref(
                    _required_value(item, "source_ref", "link_writes.source_ref"),
                    "link_writes.source_ref",
                ),
                target_ref=_uuid_ref(
                    _required_value(item, "target_ref", "link_writes.target_ref"),
                    "link_writes.target_ref",
                ),
                system=_json_object(item.get("system", {}), "link_writes.system"),
            )
            for item in _checked_objects(
                data.get("link_writes", []),
                "graph_changes.link_writes",
                {"ref", "type", "source_ref", "target_ref", "system"},
                {"link_type": "type", "source": "source_ref", "target": "target_ref"},
            )
        ),
        associate_data=tuple(
            RtgGraphAssociationChange(
                anchor_ref=_uuid_ref(
                    _required_value(item, "anchor_ref", "associate_data.anchor_ref"),
                    "associate_data.anchor_ref",
                ),
                data_ref=_uuid_ref(
                    _required_value(item, "data_ref", "associate_data.data_ref"),
                    "associate_data.data_ref",
                ),
            )
            for item in _checked_objects(
                data.get("associate_data", []),
                "graph_changes.associate_data",
                {"anchor_ref", "data_ref"},
            )
        ),
        dissociate_data=tuple(
            RtgGraphAssociationChange(
                anchor_ref=_uuid_ref(
                    _required_value(item, "anchor_ref", "dissociate_data.anchor_ref"),
                    "dissociate_data.anchor_ref",
                ),
                data_ref=_uuid_ref(
                    _required_value(item, "data_ref", "dissociate_data.data_ref"),
                    "dissociate_data.data_ref",
                ),
            )
            for item in _checked_objects(
                data.get("dissociate_data", []),
                "graph_changes.dissociate_data",
                {"anchor_ref", "data_ref"},
            )
        ),
        delete_anchors=tuple(
            _uuid_ref(item, "delete_anchors") for item in _list(data.get("delete_anchors", []))
        ),
        delete_data_objects=tuple(
            _uuid_ref(item, "delete_data_objects")
            for item in _list(data.get("delete_data_objects", []))
        ),
        delete_links=tuple(
            _uuid_ref(item, "delete_links") for item in _list(data.get("delete_links", []))
        ),
        set_live=tuple(
            RtgGraphLiveStatusChange(
                object_ref=_uuid_ref(
                    _required_value(item, "object_ref", "set_live.object_ref"),
                    "set_live.object_ref",
                ),
                live=_required_bool(item, "live"),
            )
            for item in _checked_objects(
                data.get("set_live", []),
                "graph_changes.set_live",
                {"object_ref", "live"},
            )
        ),
    )


def decode_change_batch(value: object) -> RtgChangeBatch:
    data = _object(value, "change_batch")
    _reject_unknown_keys(
        data,
        {"graph_changes", "schema_changes", "constraint_changes", "migration_changes"},
        "change_batch",
        {
            "graph": "graph_changes",
            "schema": "schema_changes",
            "constraints": "constraint_changes",
            "migrations": "migration_changes",
        },
    )
    return RtgChangeBatch(
        graph_changes=decode_graph_changes(data.get("graph_changes", {})),
        schema_changes=decode_schema_changes(data.get("schema_changes", {})),
        constraint_changes=decode_constraint_changes(data.get("constraint_changes", {})),
        migration_changes=decode_migration_changes(data.get("migration_changes", {})),
    )


def decode_schema_changes(value: object) -> RtgSchemaChangeSet:
    data = _object(value, "schema_changes")
    _reject_unknown_keys(
        data,
        {"definition_writes", "delete_definitions", "set_live"},
        "schema_changes",
        {"definitions": "definition_writes", "writes": "definition_writes"},
    )
    return RtgSchemaChangeSet(
        definition_writes=tuple(
            RtgSchemaDefinitionWrite(
                ref=_uuid_ref(
                    _required_value(item, "ref", "definition_writes.ref"),
                    "definition_writes.ref",
                ),
                definition=decode_schema_definition(
                    _required_value(item, "definition", "definition_writes.definition")
                ),
            )
            for item in _checked_objects(
                data.get("definition_writes", []),
                "schema_changes.definition_writes",
                {"ref", "definition"},
            )
        ),
        delete_definitions=tuple(
            _uuid_ref(item, "delete_definitions")
            for item in _list(data.get("delete_definitions", []))
        ),
        set_live=tuple(
            RtgLiveStatusChange(
                target_ref=_uuid_ref(
                    _required_value(item, "target_ref", "schema.set_live.target_ref"),
                    "schema.set_live.target_ref",
                ),
                live=_required_bool(item, "live"),
            )
            for item in _checked_objects(
                data.get("set_live", []),
                "schema_changes.set_live",
                {"target_ref", "live"},
            )
        ),
    )


def decode_constraint_changes(value: object) -> RtgConstraintChangeSet:
    data = _object(value, "constraint_changes")
    _reject_unknown_keys(
        data,
        {"constraint_writes", "delete_constraints", "set_live"},
        "constraint_changes",
        {"constraints": "constraint_writes", "writes": "constraint_writes"},
    )
    return RtgConstraintChangeSet(
        constraint_writes=tuple(
            RtgConstraintDefinitionWrite(
                ref=_uuid_ref(
                    _required_value(item, "ref", "constraint_writes.ref"),
                    "constraint_writes.ref",
                ),
                constraint=decode_constraint_definition(
                    _required_value(item, "constraint", "constraint_writes.constraint")
                ),
            )
            for item in _checked_objects(
                data.get("constraint_writes", []),
                "constraint_changes.constraint_writes",
                {"ref", "constraint"},
            )
        ),
        delete_constraints=tuple(
            _uuid_ref(item, "delete_constraints")
            for item in _list(data.get("delete_constraints", []))
        ),
        set_live=tuple(
            RtgLiveStatusChange(
                target_ref=_uuid_ref(
                    _required_value(item, "target_ref", "constraint.set_live.target_ref"),
                    "constraint.set_live.target_ref",
                ),
                live=_required_bool(item, "live"),
            )
            for item in _checked_objects(
                data.get("set_live", []),
                "constraint_changes.set_live",
                {"target_ref", "live"},
            )
        ),
    )


def decode_migration_changes(value: object) -> RtgMigrationChangeSet:
    data = _object(value, "migration_changes")
    _reject_unknown_keys(
        data,
        {"migration_writes", "delete_migrations", "status_changes", "evidence_additions"},
        "migration_changes",
        {"migrations": "migration_writes", "writes": "migration_writes"},
    )
    return RtgMigrationChangeSet(
        migration_writes=tuple(
            RtgMigrationRecordWrite(
                ref=_migration_ref(
                    _required_value(item, "ref", "migration_writes.ref"),
                    "migration_writes.ref",
                ),
                migration=decode_migration_record(
                    _required_value(item, "migration", "migration_writes.migration")
                ),
            )
            for item in _checked_objects(
                data.get("migration_writes", []),
                "migration_changes.migration_writes",
                {"ref", "migration"},
            )
        ),
        delete_migrations=tuple(
            _migration_ref(item, "delete_migrations")
            for item in _list(data.get("delete_migrations", []))
        ),
        status_changes=tuple(
            RtgMigrationStatusChange(
                migration_ref=_migration_ref(
                    _required_value(item, "migration_ref", "status_changes.ref"),
                    "status_changes.ref",
                ),
                status=_required_str(item, "status"),
                status_metadata=_json_object(item.get("status_metadata", {}), "status_metadata"),
            )
            for item in _checked_objects(
                data.get("status_changes", []),
                "migration_changes.status_changes",
                {"migration_ref", "status", "status_metadata"},
            )
        ),
        evidence_additions=tuple(
            RtgMigrationEvidenceAddition(
                migration_ref=_migration_ref(
                    _required_value(item, "migration_ref", "evidence_additions.ref"),
                    "evidence_additions.ref",
                ),
                evidence=decode_migration_evidence(
                    _required_value(item, "evidence", "evidence_additions.evidence")
                ),
            )
            for item in _checked_objects(
                data.get("evidence_additions", []),
                "migration_changes.evidence_additions",
                {"migration_ref", "evidence"},
            )
        ),
    )


def decode_schema_definition(value: object) -> RtgSchemaDefinition:
    data = _object(value, "schema_definition")
    _reject_unknown_keys(
        data,
        {"uuid", "kind", "type_key", "description", "payload", "system"},
        "schema_definition",
        {"type": "type_key", "name": "type_key", "schema_type": "type_key"},
    )
    kind = _required_str(data, "kind")
    payload = _object(data.get("payload", {}), "schema_definition.payload")
    if kind == "anchor":
        _reject_unknown_keys(
            payload,
            {"required_data_types", "optional_data_types"},
            "schema_definition.payload",
            {
                "required": "required_data_types",
                "optional": "optional_data_types",
                "required_data_type_keys": "required_data_types",
                "optional_data_type_keys": "optional_data_types",
            },
        )
        decoded_payload = RtgAnchorSchemaPayload(
            required_data_types=_str_tuple(
                payload.get("required_data_types", []),
                "schema_definition.payload.required_data_types",
            ),
            optional_data_types=_str_tuple(
                payload.get("optional_data_types", []),
                "schema_definition.payload.optional_data_types",
            ),
        )
    elif kind == "data_object":
        _reject_unknown_keys(
            payload,
            {"properties"},
            "schema_definition.payload",
            {"fields": "properties", "attrs": "properties"},
        )
        decoded_payload = RtgDataObjectSchemaPayload(
            properties={
                str(key): decode_schema_field(item)
                for key, item in _object(payload.get("properties", {}), "properties").items()
            }
        )
    elif kind == "link":
        _reject_unknown_keys(
            payload,
            {"allowed_source_types", "allowed_target_types"},
            "schema_definition.payload",
            {
                "source_types": "allowed_source_types",
                "target_types": "allowed_target_types",
                "allowed_sources": "allowed_source_types",
                "allowed_targets": "allowed_target_types",
            },
        )
        decoded_payload = RtgLinkSchemaPayload(
            allowed_source_types=_str_tuple(
                payload.get("allowed_source_types", []),
                "schema_definition.payload.allowed_source_types",
            ),
            allowed_target_types=_str_tuple(
                payload.get("allowed_target_types", []),
                "schema_definition.payload.allowed_target_types",
            ),
        )
    else:
        raise RtgMcpInputInvalid(f"unsupported schema definition kind: {kind}")
    return RtgSchemaDefinition(
        uuid=_optional_uuid(data.get("uuid")),
        kind=kind,
        type_key=_required_str(data, "type_key"),
        description=_required_str(data, "description"),
        payload=decoded_payload,
        system=_json_object(data.get("system", {}), "schema_definition.system"),
    )


def decode_schema_field(value: object) -> RtgSchemaField:
    data = _object(value, "schema_field")
    _reject_unknown_keys(
        data,
        {"required", "value_kinds", "properties", "items"},
        "schema_field",
        {"kind": "value_kinds", "type": "value_kinds", "types": "value_kinds"},
    )
    items = data.get("items")
    return RtgSchemaField(
        required=_required_bool(data, "required"),
        value_kinds=_str_tuple(data.get("value_kinds", []), "schema_field.value_kinds"),
        properties={
            str(key): decode_schema_field(item)
            for key, item in _object(data.get("properties", {}), "properties").items()
        },
        items=decode_schema_field(items) if items is not None else None,
    )


def decode_constraint_definition(value: object) -> RtgConstraintDefinition:
    data = _object(value, "constraint_definition")
    _reject_unknown_keys(
        data,
        {"uuid", "kind", "target_type_keys", "display_name", "description", "payload", "system"},
        "constraint_definition",
        {"type": "kind", "targets": "target_type_keys", "name": "display_name"},
    )
    kind = _required_str(data, "kind")
    payload = _object(data.get("payload", {}), "constraint_definition.payload")
    if kind == "query_pattern":
        _reject_unknown_keys(
            payload,
            {"query_spec", "expectation"},
            "constraint_definition.payload",
            {"query": "query_spec"},
        )
        decoded_payload = RtgConstraintQueryPatternPayload(
            query_spec=decode_query_spec(payload["query_spec"]),
            expectation=_required_str(payload, "expectation"),
        )
    elif kind == "cardinality":
        _reject_unknown_keys(
            payload,
            {"query_spec", "counted_binding", "minimum", "maximum"},
            "constraint_definition.payload",
            {
                "query": "query_spec",
                "binding": "counted_binding",
                "min": "minimum",
                "max": "maximum",
            },
        )
        decoded_payload = RtgConstraintCardinalityPayload(
            query_spec=decode_query_spec(payload["query_spec"]),
            counted_binding=_required_str(payload, "counted_binding"),
            minimum=_optional_int(payload.get("minimum"), "constraint_definition.payload.minimum"),
            maximum=_optional_int(payload.get("maximum"), "constraint_definition.payload.maximum"),
        )
    else:
        raise RtgMcpInputInvalid(f"unsupported constraint kind: {kind}")
    return RtgConstraintDefinition(
        uuid=_optional_uuid(data.get("uuid")),
        kind=kind,
        target_type_keys=_str_tuple(
            data.get("target_type_keys", []), "constraint_definition.target_type_keys"
        ),
        display_name=_required_str(data, "display_name"),
        description=_required_str(data, "description"),
        payload=decoded_payload,
        system=_json_object(data.get("system", {}), "constraint_definition.system"),
    )


def decode_migration_record(value: object) -> RtgMigrationRecord:
    data = _object(value, "migration_record")
    _reject_unknown_keys(
        data,
        {
            "migration_id",
            "description",
            "status",
            "schema_make_live",
            "schema_make_non_live",
            "constraint_make_live",
            "constraint_make_non_live",
            "graph_make_live",
            "graph_make_non_live",
            "schema_replacements",
            "constraint_replacements",
            "graph_replacements",
            "evidence",
            "metadata",
        },
        "migration_record",
        {
            "id": "migration_id",
            "schema_live": "schema_make_live",
            "schema_retire": "schema_make_non_live",
            "graph_live": "graph_make_live",
        },
    )
    return RtgMigrationRecord(
        migration_id=_optional_str(data.get("migration_id")),
        description=_required_str(data, "description"),
        status=_optional_str(data.get("status")) or "draft",
        schema_make_live=_uuid_tuple(
            data.get("schema_make_live", []), "migration_record.schema_make_live"
        ),
        schema_make_non_live=_uuid_tuple(
            data.get("schema_make_non_live", []), "migration_record.schema_make_non_live"
        ),
        constraint_make_live=_uuid_tuple(
            data.get("constraint_make_live", []), "migration_record.constraint_make_live"
        ),
        constraint_make_non_live=_uuid_tuple(
            data.get("constraint_make_non_live", []), "migration_record.constraint_make_non_live"
        ),
        graph_make_live=_uuid_tuple(
            data.get("graph_make_live", []), "migration_record.graph_make_live"
        ),
        graph_make_non_live=_uuid_tuple(
            data.get("graph_make_non_live", []), "migration_record.graph_make_non_live"
        ),
        schema_replacements=tuple(
            decode_migration_replacement(item)
            for item in _list(data.get("schema_replacements", []))
        ),
        constraint_replacements=tuple(
            decode_migration_replacement(item)
            for item in _list(data.get("constraint_replacements", []))
        ),
        graph_replacements=tuple(
            decode_migration_replacement(item) for item in _list(data.get("graph_replacements", []))
        ),
        evidence=tuple(decode_migration_evidence(item) for item in _list(data.get("evidence", []))),
        metadata=_json_object(data.get("metadata", {}), "migration_record.metadata"),
    )


def decode_migration_replacement(value: object) -> RtgMigrationReplacement:
    data = _object(value, "migration_replacement")
    _reject_unknown_keys(
        data,
        {"old_resource_id", "new_resource_id"},
        "migration_replacement",
        {"old": "old_resource_id", "new": "new_resource_id"},
    )
    return RtgMigrationReplacement(
        old_resource_id=_required_uuid(data, "old_resource_id"),
        new_resource_id=_required_uuid(data, "new_resource_id"),
    )


def decode_migration_evidence(value: object) -> RtgMigrationEvidence:
    data = _object(value, "migration_evidence")
    _reject_unknown_keys(
        data,
        {"evidence_id", "kind", "reference", "summary", "metadata"},
        "migration_evidence",
        {"id": "evidence_id", "ref": "reference"},
    )
    return RtgMigrationEvidence(
        evidence_id=_required_str(data, "evidence_id"),
        kind=_required_str(data, "kind"),
        reference=_required_str(data, "reference"),
        summary=_required_str(data, "summary"),
        metadata=_json_object(data.get("metadata", {}), "migration_evidence.metadata"),
    )


def decode_query_spec(value: object) -> RtgQuerySpec:
    data = _object(value, "query_spec")
    _reject_unknown_keys(
        data,
        {
            "anchor_buckets",
            "link_requirements",
            "data_requirements",
            "return_spec",
            "diagnostic_options",
        },
        "query_spec",
        {
            "returns": "return_spec",
            "return": "return_spec",
            "query_options": "top-level rtg_execute_query argument query_options",
            "response_options": "top-level rtg_execute_query argument response_options",
        },
        minimal_example={
            "query_spec": {"anchor_buckets": [{"name": "item", "anchor_type_keys": ["Item"]}]},
            "query_options": {"live_filter": "live"},
            "response_options": {"format": "properties_only"},
        },
        guide_topics=("tool_call_shapes", "query_examples"),
    )
    return RtgQuerySpec(
        anchor_buckets=tuple(
            _decode_query_anchor_bucket(item, index)
            for index, item in enumerate(
                _list(data.get("anchor_buckets", []), "query_spec.anchor_buckets")
            )
        ),
        link_requirements=tuple(
            _decode_query_link_requirement(item, index)
            for index, item in enumerate(
                _list(data.get("link_requirements", []), "query_spec.link_requirements")
            )
        ),
        data_requirements=tuple(
            _decode_query_data_requirement(item, index)
            for index, item in enumerate(
                _list(data.get("data_requirements", []), "query_spec.data_requirements")
            )
        ),
        return_spec=decode_query_return_spec(data.get("return_spec", {})),
        diagnostic_options=decode_query_diagnostic_options(data.get("diagnostic_options", {})),
    )


def _decode_query_anchor_bucket(value: object, index: int) -> RtgQueryAnchorBucket:
    label = f"query_spec.anchor_buckets[{index}]"
    data = _object(value, label)
    _reject_unknown_keys(
        data,
        {"name", "anchor_type_keys"},
        label,
        {"binding": "name", "type": "anchor_type_keys", "types": "anchor_type_keys"},
    )
    return RtgQueryAnchorBucket(
        name=_required_str(data, "name"),
        anchor_type_keys=_str_tuple(data.get("anchor_type_keys", []), f"{label}.anchor_type_keys"),
    )


def _decode_query_link_requirement(value: object, index: int) -> RtgQueryLinkRequirement:
    label = f"query_spec.link_requirements[{index}]"
    data = _object(value, label)
    _reject_unknown_keys(
        data,
        {"name", "source_bucket", "target_bucket", "link_type_keys"},
        label,
        {
            "source": "source_bucket",
            "target": "target_bucket",
            "type": "link_type_keys",
            "types": "link_type_keys",
        },
    )
    return RtgQueryLinkRequirement(
        name=_required_str(data, "name"),
        source_bucket=_required_str(data, "source_bucket"),
        target_bucket=_required_str(data, "target_bucket"),
        link_type_keys=_str_tuple(data.get("link_type_keys", []), f"{label}.link_type_keys"),
    )


def _decode_query_data_requirement(value: object, index: int) -> RtgQueryDataRequirement:
    label = f"query_spec.data_requirements[{index}]"
    data = _object(value, label)
    _reject_unknown_keys(
        data,
        {"name", "anchor_bucket", "data_type_key", "required", "predicates"},
        label,
        {
            "binding": "name",
            "bucket": "anchor_bucket",
            "type": "data_type_key",
            "data_type": "data_type_key",
            "property_predicates": "predicates",
            "filters": "predicates",
        },
    )
    return RtgQueryDataRequirement(
        name=_required_str(data, "name"),
        anchor_bucket=_required_str(data, "anchor_bucket"),
        data_type_key=_required_str(data, "data_type_key"),
        required=_optional_bool(data.get("required"), True, f"{label}.required"),
        predicates=tuple(
            decode_query_property_predicate(predicate)
            for predicate in _list(data.get("predicates", []), f"{label}.predicates")
        ),
    )


def decode_query_options(value: object | None) -> RtgQueryOptions | None:
    if value is None:
        return None
    data = _object(value, "query_options")
    _reject_unknown_keys(
        data,
        {"live_filter", "live_status_overlay", "order_by"},
        "query_options",
    )
    overlay = _object(data.get("live_status_overlay", {}), "live_status_overlay")
    return RtgQueryOptions(
        live_filter=_optional_str(data.get("live_filter")) or "all",
        live_status_overlay={UUID(str(key)): _bool(item) for key, item in overlay.items()},
        order_by=tuple(
            _decode_query_order_by(item, index)
            for index, item in enumerate(_list(data.get("order_by", []), "query_options.order_by"))
        ),
    )


def _decode_query_order_by(value: object, index: int) -> RtgQueryOrderBy:
    label = f"query_options.order_by[{index}]"
    data = _object(value, label)
    _reject_unknown_keys(data, {"data_requirement", "path", "direction"}, label)
    direction = _optional_str(data.get("direction")) or "ascending"
    if direction in {"asc", "ASC"}:
        direction = "ascending"
    elif direction in {"desc", "DESC"}:
        direction = "descending"
    return RtgQueryOrderBy(
        data_requirement=_required_str(data, "data_requirement"),
        path=_str_tuple(data.get("path", []), f"{label}.path"),
        direction=direction,
    )


def decode_query_property_predicate(value: object) -> RtgQueryPropertyPredicate:
    data = _object(value, "query_predicate")
    _reject_unknown_keys(
        data,
        {"path", "operator", "value", "values", "case_sensitive", "regex_flags"},
        "query_predicate",
        {"property": "path", "property_path": "path", "field": "path", "op": "operator"},
    )
    return RtgQueryPropertyPredicate(
        path=_str_tuple(data.get("path", []), "query_predicate.path"),
        operator=_required_str(data, "operator"),
        value=cast(JsonValue, data.get("value")),
        values=tuple(
            cast(str | int | float | bool | None, item) for item in _list(data.get("values", []))
        ),
        case_sensitive=_optional_bool(
            data.get("case_sensitive"), False, "query_predicate.case_sensitive"
        ),
        regex_flags=_str_tuple(data.get("regex_flags", []), "query_predicate.regex_flags"),
    )


def decode_query_return_spec(value: object) -> RtgQueryReturnSpec:
    data = _object(value, "query_return_spec")
    _reject_unknown_keys(
        data,
        {"anchor_buckets", "link_requirements", "data_requirements", "properties"},
        "query_return_spec",
        {
            "anchors": "anchor_buckets",
            "links": "link_requirements",
            "data": "data_requirements",
            "fields": "properties",
        },
    )
    return RtgQueryReturnSpec(
        anchor_buckets=_str_tuple(
            data.get("anchor_buckets", []), "query_return_spec.anchor_buckets"
        ),
        link_requirements=_str_tuple(
            data.get("link_requirements", []), "query_return_spec.link_requirements"
        ),
        data_requirements=_str_tuple(
            data.get("data_requirements", []), "query_return_spec.data_requirements"
        ),
        properties=tuple(
            _decode_query_return_property(item, index)
            for index, item in enumerate(
                _list(data.get("properties", []), "query_return_spec.properties")
            )
        ),
    )


def _decode_query_return_property(value: object, index: int) -> tuple[str, tuple[str, ...]]:
    pair = _list(value, f"query_return_spec.properties[{index}]")
    if len(pair) != 2:
        raise RtgMcpInputInvalid(
            f"query_return_spec.properties[{index}] must be [data_requirement_name, path]"
        )
    path = _list(pair[1], f"query_return_spec.properties[{index}][1]")
    if not isinstance(pair[0], str):
        raise RtgMcpInputInvalid(f"query_return_spec.properties[{index}][0] must be a string")
    return pair[0], _str_tuple(path, f"query_return_spec.properties[{index}][1]")


def decode_query_diagnostic_options(value: object) -> RtgQueryDiagnosticOptions:
    data = _object(value, "query_diagnostic_options")
    _reject_unknown_keys(
        data,
        {"include_non_fatal", "unknown_term_guidance"},
        "query_diagnostic_options",
    )
    return RtgQueryDiagnosticOptions(
        include_non_fatal=_optional_bool(
            data.get("include_non_fatal"),
            True,
            "query_diagnostic_options.include_non_fatal",
        ),
        unknown_term_guidance=_optional_str(data.get("unknown_term_guidance"))
        or "suggest_discovery",
    )


def decode_cutover_options(value: object | None) -> RtgControllerCutoverOptions | None:
    if value is None:
        return None
    data = _object(value, "cutover_options")
    _reject_unknown_keys(
        data,
        {"validation_mode", "prune_retired", "failure_restore"},
        "cutover_options",
    )
    return RtgControllerCutoverOptions(
        validation_mode=_optional_str(data.get("validation_mode")) or "strict",
        prune_retired=_optional_bool(
            data.get("prune_retired"), True, "cutover_options.prune_retired"
        ),
        failure_restore=_optional_str(data.get("failure_restore"))
        or "restore_pre_cutover_snapshot",
    )


def decode_validation_options(value: object | None) -> RtgControllerValidationOptions | None:
    if value is None:
        return None
    data = _object(value, "validation_options")
    _reject_unknown_keys(
        data,
        {"tracks", "finding_limit"},
        "validation_options",
        {
            "mode": (
                "validation_options.tracks or validation_options.finding_limit; dry-run "
                "tools do not accept validation_options.mode, and mutation tools use "
                "top-level validation_mode"
            ),
            "validation_mode": (
                "top-level validation_mode on mutation tools; dry-run tools accept only "
                "validation_options.tracks and validation_options.finding_limit"
            ),
        },
        minimal_example={"validation_options": {"tracks": "all", "finding_limit": 20}},
        guide_topics=("tool_call_shapes", "live_write"),
    )
    tracks = data.get("tracks", "all")
    return RtgControllerValidationOptions(
        tracks="all" if tracks == "all" else _str_tuple(tracks, "validation_options.tracks"),
        finding_limit=_optional_int(data.get("finding_limit"), "validation_options.finding_limit"),
    )


def decode_discovery_options(value: object | None) -> RtgControllerDiscoveryOptions | None:
    if value is None:
        return None
    data = _object(value, "discovery_options")
    _reject_unknown_keys(data, {"include_non_live", "limit"}, "discovery_options")
    return RtgControllerDiscoveryOptions(
        include_non_live=_optional_bool(
            data.get("include_non_live"), False, "discovery_options.include_non_live"
        ),
        limit=_optional_int(data.get("limit"), "discovery_options.limit"),
    )


def decode_schema_pack_options(value: object | None) -> RtgControllerSchemaPackOptions | None:
    if value is None:
        return None
    data = _object(value, "schema_pack_options")
    _reject_unknown_keys(
        data,
        {"live", "include_live_counts"},
        "schema_pack_options",
        {"include_counts": "include_live_counts"},
    )
    live = data.get("live", True)
    return RtgControllerSchemaPackOptions(
        live=None if live is None else _bool(live),
        include_live_counts=_optional_bool(
            data.get("include_live_counts"),
            True,
            "schema_pack_options.include_live_counts",
        ),
    )


def decode_replay_options(value: object | None) -> RtgControllerReplayOptions | None:
    if value is None:
        return None
    data = _object(value, "replay_options")
    _reject_unknown_keys(
        data,
        {
            "start_snapshot",
            "start_snapshot_path",
            "after_ledger_position",
            "through_ledger_position",
        },
        "replay_options",
        {
            "snapshot": "start_snapshot",
            "snapshot_path": "start_snapshot_path",
            "after": "after_ledger_position",
            "through": "through_ledger_position",
        },
    )
    snapshot = data.get("start_snapshot")
    return RtgControllerReplayOptions(
        start_snapshot=decode_system_snapshot(snapshot) if snapshot is not None else None,
        start_snapshot_path=_optional_str(data.get("start_snapshot_path")),
        after_ledger_position=_optional_int(
            data.get("after_ledger_position"), "replay_options.after_ledger_position"
        ),
        through_ledger_position=_optional_int(
            data.get("through_ledger_position"), "replay_options.through_ledger_position"
        ),
    )


def decode_restore_options(value: object | None) -> RtgControllerRestoreOptions | None:
    if value is None:
        return None
    data = _object(value, "restore_options")
    _reject_unknown_keys(data, {"ledger_mode"}, "restore_options")
    return RtgControllerRestoreOptions(
        ledger_mode=_optional_str(data.get("ledger_mode")) or "record"
    )


def decode_system_snapshot(value: object) -> RtgSystemSnapshot:
    data = _object(value, "system_snapshot")
    return RtgSystemSnapshot(
        graph=decode_graph_snapshot(_required_value(data, "graph", "system_snapshot.graph")),
        schema=decode_schema_snapshot(_required_value(data, "schema", "system_snapshot.schema")),
        constraints=decode_constraint_snapshot(
            _required_value(data, "constraints", "system_snapshot.constraints")
        ),
        migration=decode_migration_snapshot(
            _required_value(data, "migration", "system_snapshot.migration")
        ),
        last_ledger_position=_optional_int(
            data.get("last_ledger_position"), "system_snapshot.last_ledger_position"
        ),
        last_transaction_id=_optional_uuid(data.get("last_transaction_id")),
        last_transaction_timestamp=_optional_str(data.get("last_transaction_timestamp")),
    )


def decode_graph_snapshot(value: object) -> RtgGraphSnapshot:
    data = _object(value, "graph_snapshot")
    anchor_data_index = _object(data.get("anchor_data_index", {}), "anchor_data_index")
    return RtgGraphSnapshot(
        anchors=tuple(
            _json_object(item, "graph_snapshot.anchors") for item in _list(data.get("anchors", []))
        ),
        data_objects=tuple(
            _json_object(item, "graph_snapshot.data_objects")
            for item in _list(data.get("data_objects", []))
        ),
        links=tuple(
            _json_object(item, "graph_snapshot.links") for item in _list(data.get("links", []))
        ),
        anchor_data_index={
            str(key): tuple(str(item) for item in _list(items, "anchor_data_index"))
            for key, items in anchor_data_index.items()
        },
    )


def decode_schema_snapshot(value: object) -> RtgSchemaSnapshot:
    data = _object(value, "schema_snapshot")
    return RtgSchemaSnapshot(
        definitions=tuple(
            _json_object(item, "schema_snapshot.definitions")
            for item in _list(data.get("definitions", []))
        )
    )


def decode_constraint_snapshot(value: object) -> RtgConstraintSnapshot:
    data = _object(value, "constraint_snapshot")
    return RtgConstraintSnapshot(
        constraints=tuple(
            decode_constraint_definition(item) for item in _list(data.get("constraints", []))
        )
    )


def decode_migration_snapshot(value: object) -> RtgMigrationSnapshot:
    data = _object(value, "migration_snapshot")
    return RtgMigrationSnapshot(
        migrations=tuple(
            decode_migration_record(item) for item in _list(data.get("migrations", []))
        )
    )


def _uuid_ref(value: object, label: str) -> RtgChangeReference:
    if isinstance(value, str):
        raise RtgMcpInputInvalid(
            f'{label} must be an object like {{"resource_id": "<uuid>"}} '
            f'or {{"local_ref": "<request-local-name>"}}, not a string',
            diagnostic=rtg_diagnostic(
                code="mcp.input.ref_shape",
                category="input_shape",
                path=label,
                problem="Object references must be JSON objects, not bare strings.",
                remedy=(
                    'Use {"local_ref": "<request-local-name>"} for objects created in the same '
                    'request, or {"resource_id": "<uuid>"} for objects returned by earlier calls.'
                ),
                accepted_fields=("local_ref", "resource_id"),
                minimal_example={"ref": {"local_ref": "item-alpha"}},
                guide_topics=("workflow_patterns", "live_write", "lookup_examples"),
            ),
        )
    data = _object(value, label)
    _reject_unknown_keys(
        data, {"resource_id", "local_ref"}, label, {"id": "resource_id", "ref": "local_ref"}
    )
    _ensure_one_ref_identity(data, label)
    return RtgChangeReference(
        resource_id=_optional_uuid(data.get("resource_id")),
        local_ref=_optional_str(data.get("local_ref")),
    )


def _migration_ref(value: object, label: str) -> RtgChangeReference:
    if isinstance(value, str):
        raise RtgMcpInputInvalid(
            f'{label} must be an object like {{"resource_id": "<migration-id>"}} '
            f'or {{"local_ref": "<request-local-name>"}}, not a string',
            diagnostic=rtg_diagnostic(
                code="mcp.input.ref_shape",
                category="input_shape",
                path=label,
                problem="Migration references must be JSON objects, not bare strings.",
                remedy=(
                    'Use {"resource_id": "<migration-id>"} for existing migrations or '
                    '{"local_ref": "<request-local-name>"} inside one request.'
                ),
                accepted_fields=("local_ref", "resource_id"),
                minimal_example={"migration_ref": {"resource_id": "migration-id"}},
                guide_topics=("workflow_patterns", "schema_staging_minimal", "migration_history"),
            ),
        )
    data = _object(value, label)
    _reject_unknown_keys(
        data, {"resource_id", "local_ref"}, label, {"id": "resource_id", "ref": "local_ref"}
    )
    _ensure_one_ref_identity(data, label)
    resource_id = data.get("resource_id")
    return RtgChangeReference(
        resource_id=_optional_str(resource_id),
        local_ref=_optional_str(data.get("local_ref")),
    )


def _ensure_one_ref_identity(data: dict[str, object], label: str) -> None:
    if ("resource_id" in data) == ("local_ref" in data):
        raise RtgMcpInputInvalid(
            f"{label} needs exactly one of resource_id or local_ref",
            diagnostic=rtg_diagnostic(
                code="mcp.input.ref_identity",
                category="input_shape",
                path=label,
                problem="A reference must use exactly one identity form.",
                remedy=(
                    "Use local_ref only within the request that creates the object; use "
                    "resource_id for existing objects returned by earlier calls."
                ),
                accepted_fields=("local_ref", "resource_id"),
                minimal_example={"ref": {"resource_id": "11111111-1111-1111-1111-111111111111"}},
                guide_topics=("workflow_patterns", "live_write", "lookup_examples"),
            ),
        )


def _object(value: object, label: str = "value") -> dict[str, object]:
    if not isinstance(value, dict):
        raise RtgMcpInputInvalid(
            f"{label} must be an object",
            diagnostic=_shape_diagnostic(
                code="mcp.input.object_required",
                path=label,
                problem="This MCP argument must be a JSON object.",
                remedy="Send an object with the accepted fields for this tool call.",
            ),
        )
    return cast(dict[str, object], value)


def _checked_objects(
    value: object,
    label: str,
    allowed: set[str],
    hints: dict[str, str] | None = None,
) -> tuple[dict[str, object], ...]:
    return tuple(
        _checked_object(item, f"{label}[{index}]", allowed, hints)
        for index, item in enumerate(_list(value, label))
    )


def _checked_object(
    value: object,
    label: str,
    allowed: set[str],
    hints: dict[str, str] | None = None,
) -> dict[str, object]:
    data = _object(value, label)
    _reject_unknown_keys(data, allowed, label, hints)
    return data


def _list(value: object, label: str = "value") -> list[object]:
    if not isinstance(value, list | tuple):
        raise RtgMcpInputInvalid(
            f"{label} must be a list",
            diagnostic=_shape_diagnostic(
                code="mcp.input.list_required",
                path=label,
                problem="This MCP argument must be a JSON list.",
                remedy="Send a list, even when there is only one item.",
            ),
        )
    return list(value)


def _json_object(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise RtgMcpInputInvalid(
            f"{label} must be an object",
            diagnostic=_shape_diagnostic(
                code="mcp.input.object_required",
                path=label,
                problem="This field must be a JSON object.",
                remedy="Send an object for this field.",
            ),
        )
    return cast(JsonObject, dict(value))


def _reject_unknown_keys(
    data: dict[str, object],
    allowed: set[str],
    label: str,
    hints: dict[str, str] | None = None,
    minimal_example: JsonObject | None = None,
    guide_topics: tuple[str, ...] = (),
) -> None:
    unknown = sorted(set(data) - allowed)
    if not unknown:
        return

    hints = hints or {}
    details = [f"{key!r} (use {hints[key]!r})" if key in hints else repr(key) for key in unknown]
    first_unknown = unknown[0]
    remedy = (
        f"Use {hints[first_unknown]} for {first_unknown!r}."
        if first_unknown in hints
        else f"Remove unsupported field(s) and use only accepted fields for {label}."
    )
    raise RtgMcpInputInvalid(
        f"{label} has unsupported field(s): {', '.join(details)}",
        diagnostic=rtg_diagnostic(
            code="mcp.input.unsupported_field",
            category="input_shape",
            path=f"{label}.{first_unknown}",
            problem=f"{label} contains unsupported field(s): {', '.join(unknown)}",
            remedy=remedy,
            accepted_fields=tuple(sorted(allowed)),
            minimal_example=minimal_example,
            guide_topics=guide_topics,
        ),
    )


def _required_str(data: dict[str, object], key: str) -> str:
    try:
        value = data[key]
    except KeyError as error:
        raise _required_field_error(key) from error
    if not isinstance(value, str):
        raise _type_error(key, "string", f"{key} must be a string")
    return value


def _required_value(data: dict[str, object], key: str, label: str) -> object:
    try:
        return data[key]
    except KeyError as error:
        raise _required_field_error(label) from error


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _type_error("value", "string or null", "value must be a string or null")
    return value


def _required_bool(data: dict[str, object], key: str, label: str | None = None) -> bool:
    path = label or key
    try:
        return _bool(data[key], path)
    except KeyError as error:
        raise _required_field_error(path) from error


def _bool(value: object, label: str = "value") -> bool:
    if not isinstance(value, bool):
        raise _type_error(label, "boolean", f"{label} must be boolean")
    return value


def _optional_bool(value: object, default: bool, label: str = "value") -> bool:
    return default if value is None else _bool(value, label)


def _required_uuid(data: dict[str, object], key: str, label: str | None = None) -> UUID:
    path = label or key
    try:
        value = data[key]
    except KeyError as error:
        raise RtgMcpInputInvalid(f"{path} is required") from error
    try:
        return UUID(str(value))
    except ValueError as error:
        raise RtgMcpInputInvalid(
            f"{path} must be a UUID",
            diagnostic=rtg_diagnostic(
                code="mcp.input.uuid",
                category="input_shape",
                path=path,
                problem="Expected a UUID string.",
                remedy="Use a UUID returned by an earlier RTG tool call; do not invent IDs.",
                minimal_example={path: "11111111-1111-1111-1111-111111111111"},
                guide_topics=("lookup_examples",),
            ),
        ) from error


def _optional_uuid(value: object, label: str = "value") -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError as error:
        raise RtgMcpInputInvalid(
            f"{label} must be a UUID or null",
            diagnostic=rtg_diagnostic(
                code="mcp.input.uuid",
                category="input_shape",
                path=label,
                problem="Expected a UUID string or null.",
                remedy="Use a UUID returned by an earlier RTG tool call; do not invent IDs.",
                minimal_example={label: "11111111-1111-1111-1111-111111111111"},
                guide_topics=("lookup_examples",),
            ),
        ) from error


def _uuid_tuple(value: object, label: str = "value") -> tuple[UUID, ...]:
    uuids: list[UUID] = []
    for index, item in enumerate(_list(value, label)):
        try:
            uuids.append(UUID(str(item)))
        except ValueError as error:
            raise RtgMcpInputInvalid(
                f"{label}[{index}] must be a UUID",
                diagnostic=rtg_diagnostic(
                    code="mcp.input.uuid",
                    category="input_shape",
                    path=f"{label}[{index}]",
                    problem="Expected every item in this list to be a UUID string.",
                    remedy=(
                        "Use candidate UUIDs returned by staging tools or object UUIDs returned "
                        "by queries."
                    ),
                    minimal_example={label: ["11111111-1111-1111-1111-111111111111"]},
                    guide_topics=("schema_staging_minimal", "tool_call_shapes"),
                ),
            ) from error
    return tuple(uuids)


def _str_tuple(value: object, label: str = "value") -> tuple[str, ...]:
    values = _list(value, label)
    strings: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, str):
            raise _type_error(
                f"{label}[{index}]",
                "string",
                f"{label}[{index}] must be a string",
            )
        strings.append(item)
    return tuple(strings)


def _optional_int(value: object, label: str = "value") -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise _type_error(label, "integer or null", f"{label} must be an integer or null")
    return value


def _required_field_error(path: str) -> RtgMcpInputInvalid:
    return RtgMcpInputInvalid(
        f"{path} is required",
        diagnostic=_shape_diagnostic(
            code="mcp.input.required_field",
            path=path,
            problem="A required MCP input field is missing.",
            remedy="Add the required field at the reported path and retry the same tool call.",
        ),
    )


def _type_error(path: str, expected: str, message: str) -> RtgMcpInputInvalid:
    return RtgMcpInputInvalid(
        message,
        diagnostic=_shape_diagnostic(
            code="mcp.input.type_mismatch",
            path=path,
            problem=f"Expected {expected} at this path.",
            remedy="Change the value to the expected JSON type and retry the tool call.",
        ),
    )


def _shape_diagnostic(
    *,
    code: str,
    path: str,
    problem: str,
    remedy: str,
) -> JsonObject:
    return rtg_diagnostic(
        code=code,
        category="input_shape",
        path=path,
        problem=problem,
        remedy=remedy,
        guide_topics=("tool_call_shapes",),
    )
