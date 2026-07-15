from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from uuid import UUID

from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    RtgChangeReference,
    RtgGraphAnchorWrite,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
    RtgGraphLinkWrite,
)
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import (
    InProcessRtgController,
    RtgControllerRestoreOptions,
    RtgSystemSnapshot,
)
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.graph.protocol import JsonObject, RtgGraphSnapshot
from components.rtg.migration import InMemoryRtgMigration
from components.rtg.query import SimpleRtgQueryEngine
from components.storage.json_file import LocalJsonFileStorage
from components.storage.sql import SqliteStorage
from tools.repo_twin.model import (
    SNAPSHOT_PATH,
    AnchorRecord,
    DataRecord,
    LinkRecord,
    ScanResult,
    SyncSummary,
    managed_system,
)
from tools.repo_twin.schema import build_schema

_KERNEL_SYSTEM_FIELDS = {"created_at", "updated_at"}
_LINK_SNAPSHOT_KEYS = {"uuid", "type", "source_uuid", "target_uuid"}


def open_controller(storage_root: Path, *, load_snapshot: bool = True) -> InProcessRtgController:
    storage_root.mkdir(parents=True, exist_ok=True)
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(storage_root),
        SqliteStorage.open(storage_root / "controller.sqlite"),
    )
    if load_snapshot:
        try:
            snapshot = controller.load_persisted_snapshot(SNAPSHOT_PATH).snapshot
        except Exception:
            return controller
        controller.restore_from_snapshot(
            _normalize_legacy_snapshot(snapshot),
            RtgControllerRestoreOptions(ledger_mode="skip"),
        )
    return controller


def _normalize_legacy_snapshot(snapshot: RtgSystemSnapshot) -> RtgSystemSnapshot:
    snapshot = _normalize_legacy_link_snapshot(snapshot)
    data_objects = []
    for item in snapshot.graph.data_objects:
        normalized = dict(item)
        properties = normalized.get("properties")
        if isinstance(properties, dict):
            normalized_properties = dict(properties)
            field = (
                "spec_section_hashes"
                if normalized.get("type") == "twin.ComponentFact"
                else "subject_hashes"
                if normalized.get("type") == "twin.EvidenceRecord"
                else None
            )
            if field is not None and isinstance(normalized_properties.get(field), dict):
                normalized_properties[field] = json.dumps(
                    normalized_properties[field], sort_keys=True
                )
            normalized["properties"] = normalized_properties
        data_objects.append(normalized)
    graph = dataclasses.replace(snapshot.graph, data_objects=tuple(data_objects))
    return dataclasses.replace(
        snapshot,
        graph=graph,
        schema=build_schema().export_snapshot(),
    )


def _normalize_legacy_link_snapshot(snapshot: RtgSystemSnapshot) -> RtgSystemSnapshot:
    graph = snapshot.graph
    links = tuple(
        {key: value for key, value in link.items() if key in _LINK_SNAPSHOT_KEYS}
        for link in graph.links
    )
    if links == graph.links:
        return snapshot
    return dataclasses.replace(
        snapshot,
        graph=RtgGraphSnapshot(
            anchors=graph.anchors,
            data_objects=graph.data_objects,
            links=links,
            anchor_data_index=graph.anchor_data_index,
        ),
    )


def sync_scan(scan: ScanResult, storage_root: Path) -> SyncSummary:
    if scan.parse_issues:
        raise ValueError("cannot sync a repo twin scan with parse issues")
    controller = open_controller(storage_root)
    snapshot = controller.export_system_snapshot().graph
    data_version_tokens = {
        str(item["uuid"]): controller.get_object(str(item["uuid"])).version_token
        for item in snapshot.data_objects
    }
    summary, changes = plan_sync(scan, snapshot, data_version_tokens=data_version_tokens)
    if changes is not None:
        controller.apply_live_graph_changes(changes)
    controller.persist_system_snapshot(SNAPSHOT_PATH)
    return summary


def plan_sync(
    scan: ScanResult,
    snapshot: RtgGraphSnapshot,
    *,
    data_version_tokens: dict[str, str | None] | None = None,
    materialize_changes: bool = True,
) -> tuple[SyncSummary, RtgGraphChangeSet | None]:
    data_version_tokens = data_version_tokens or {}
    existing_anchors = {
        str(item["uuid"]): _without_kernel_system_fields(item) for item in snapshot.anchors
    }
    existing_data = {
        str(item["uuid"]): _without_kernel_system_fields(item) for item in snapshot.data_objects
    }
    existing_links = {
        str(item["uuid"]): {
            key: value for key, value in item.items() if key in _LINK_SNAPSHOT_KEYS
        }
        for item in snapshot.links
    }
    existing_anchor_data = {
        anchor_uuid: tuple(data_uuids)
        for anchor_uuid, data_uuids in snapshot.anchor_data_index.items()
    }

    desired_anchors = {_uuid_text(item.uuid): _anchor_json(item) for item in scan.anchors}
    desired_data = {_uuid_text(item.uuid): _data_json(item) for item in scan.data_objects}
    desired_links = {_uuid_text(item.uuid): _link_json(item) for item in scan.links}
    desired_data_anchors = {
        _uuid_text(item.uuid): tuple(
            sorted(_uuid_text(_natural_uuid(key)) for key in item.anchor_keys)
        )
        for item in scan.data_objects
    }

    anchor_writes: list[RtgGraphAnchorWrite] = []
    data_writes: list[RtgGraphDataObjectWrite] = []
    link_writes: list[RtgGraphLinkWrite] = []
    created = 0
    updated = 0

    for record in scan.anchors:
        desired = desired_anchors[_uuid_text(record.uuid)]
        existing = existing_anchors.get(_uuid_text(record.uuid))
        if existing != desired:
            if existing is None:
                created += 1
            else:
                updated += 1
            anchor_writes.append(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(resource_id=record.uuid),
                    type=record.type_key,
                    display_name=record.display_name,
                    system=managed_system(record.natural_key),
                )
            )

    for record in scan.data_objects:
        uuid_text = _uuid_text(record.uuid)
        desired = desired_data[uuid_text]
        existing = existing_data.get(uuid_text)
        existing_anchors_for_data = tuple(
            sorted(
                anchor_uuid
                for anchor_uuid, data_uuids in existing_anchor_data.items()
                if uuid_text in data_uuids
            )
        )
        desired_anchors_for_data = desired_data_anchors[uuid_text]
        if (
            not _data_equivalent(existing, desired)
            or existing_anchors_for_data != desired_anchors_for_data
        ):
            if existing is None:
                created += 1
            else:
                updated += 1
            authority = str(record.properties.get("authority", "repo"))
            expected_version = data_version_tokens.get(uuid_text)
            if materialize_changes and existing is not None and not expected_version:
                raise RuntimeError(f"missing version token for existing data object {uuid_text}")
            data_writes.append(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=record.uuid),
                    type=record.type_key,
                    mode="replace" if existing is not None and expected_version else "merge",
                    expected_version=expected_version if materialize_changes else None,
                    properties=record.properties,
                    system=managed_system(record.natural_key, authority=authority),
                    anchor_refs=tuple(
                        RtgChangeReference(resource_id=_natural_uuid(key))
                        for key in record.anchor_keys
                    ),
                )
            )

    for record in scan.links:
        desired = desired_links[_uuid_text(record.uuid)]
        existing = existing_links.get(_uuid_text(record.uuid))
        if existing != desired:
            if existing is None:
                created += 1
            else:
                updated += 1
            link_writes.append(
                RtgGraphLinkWrite(
                    ref=RtgChangeReference(resource_id=record.uuid),
                    type=record.type_key,
                    source_ref=RtgChangeReference(resource_id=_natural_uuid(record.source_key)),
                    target_ref=RtgChangeReference(resource_id=_natural_uuid(record.target_key)),
                )
            )

    delete_links = tuple(
        RtgChangeReference(resource_id=UUID(uuid_text))
        for uuid_text, item in sorted(existing_links.items())
        if _is_prunable(item) and uuid_text not in desired_links
    )
    delete_data = tuple(
        RtgChangeReference(resource_id=UUID(uuid_text))
        for uuid_text, item in sorted(existing_data.items())
        if _is_prunable(item) and uuid_text not in desired_data
    )
    delete_anchors = tuple(
        RtgChangeReference(resource_id=UUID(uuid_text))
        for uuid_text, item in sorted(existing_anchors.items())
        if _is_prunable(item) and uuid_text not in desired_anchors
    )
    pruned = len(delete_links) + len(delete_data) + len(delete_anchors)

    summary = SyncSummary(
        created=created,
        updated=updated,
        pruned=pruned,
        anchors=len(scan.anchors),
        data_objects=len(scan.data_objects),
        links=len(scan.links),
    )
    if not summary.changed or not materialize_changes:
        return summary, None
    return (
        summary,
        RtgGraphChangeSet(
            anchor_writes=tuple(anchor_writes),
            data_object_writes=tuple(data_writes),
            link_writes=tuple(link_writes),
            delete_links=delete_links,
            delete_data_objects=delete_data,
            delete_anchors=delete_anchors,
        ),
    )


def snapshot_loaded(storage_root: Path) -> bool:
    try:
        open_controller(storage_root, load_snapshot=True).load_persisted_snapshot(SNAPSHOT_PATH)
    except Exception:
        return False
    return True


def current_snapshot(storage_root: Path) -> RtgGraphSnapshot:
    return open_controller(storage_root).export_system_snapshot().graph


def _anchor_json(record: AnchorRecord) -> JsonObject:
    result: JsonObject = {
        "uuid": _uuid_text(record.uuid),
        "type": record.type_key,
        "system": managed_system(record.natural_key),
    }
    if record.display_name is not None:
        result["display_name"] = record.display_name
    return result


def _data_json(record: DataRecord) -> JsonObject:
    authority = str(record.properties.get("authority", "repo"))
    return {
        "uuid": _uuid_text(record.uuid),
        "type": record.type_key,
        "properties": record.properties,
        "system": managed_system(record.natural_key, authority=authority),
    }


def _without_kernel_system_fields(item: JsonObject) -> JsonObject:
    normalized = dict(item)
    system = normalized.get("system")
    if isinstance(system, dict):
        normalized["system"] = {
            key: value for key, value in system.items() if key not in _KERNEL_SYSTEM_FIELDS
        }
    return normalized


def _link_json(record: LinkRecord) -> JsonObject:
    return {
        "uuid": _uuid_text(record.uuid),
        "type": record.type_key,
        "source_uuid": _uuid_text(_natural_uuid(record.source_key)),
        "target_uuid": _uuid_text(_natural_uuid(record.target_key)),
    }


def _is_prunable(item: JsonObject) -> bool:
    system = item.get("system")
    if not isinstance(system, dict):
        return False
    return system.get("twin_managed") == "repo_twin" and system.get("authority") != "evidence"


def _data_equivalent(existing: JsonObject | None, desired: JsonObject) -> bool:
    if existing is None:
        return False
    return _without_indexed_at(existing) == _without_indexed_at(desired)


def _without_indexed_at(item: JsonObject) -> JsonObject:
    copied = dict(item)
    properties = copied.get("properties")
    if isinstance(properties, dict):
        normalized_properties = dict(properties)
        normalized_properties.pop("last_indexed_at", None)
        copied["properties"] = normalized_properties
    return copied


def _natural_uuid(natural_key: str) -> UUID:
    from tools.repo_twin.model import twin_uuid

    return twin_uuid(natural_key)


def _uuid_text(uuid_value: UUID) -> str:
    return str(uuid_value)
