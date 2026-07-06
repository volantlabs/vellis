from __future__ import annotations

import copy
import json
from collections.abc import Iterable
from uuid import UUID, uuid4

from components.rtg.graph.protocol import (
    JsonObject,
    JsonValue,
    RtgAnchor,
    RtgAnchorList,
    RtgDataObject,
    RtgDataObjectList,
    RtgGraphAnchorDataIndexEntryNotFound,
    RtgGraphAnchorNotFound,
    RtgGraphDataObjectNotFound,
    RtgGraphDeleteResult,
    RtgGraphEndpointNotFound,
    RtgGraphJsonValueInvalid,
    RtgGraphLinkNotFound,
    RtgGraphObjectNotFound,
    RtgGraphReferenceInvalid,
    RtgGraphSnapshot,
    RtgGraphSnapshotInvalid,
    RtgGraphSystemValueInvalid,
    RtgGraphTypeInvalid,
    RtgGraphTypeKindConflict,
    RtgGraphUuidConflict,
    RtgGraphUuidInvalid,
    RtgLink,
    RtgLinkList,
    RtgObject,
    RtgObjectList,
    RtgTypeCount,
    RtgTypeCountList,
    UuidInput,
)

_ANCHOR_KIND = "anchor"
_DATA_KIND = "data_object"
_LINK_KIND = "link"
_VALID_KINDS = {_ANCHOR_KIND, _DATA_KIND, _LINK_KIND}
_VALID_DIRECTIONS = {"source", "target", "both"}


class InMemoryRtgGraph:
    """In-memory implementation of the Reified Type Graph component."""

    def __init__(self) -> None:
        self._anchors: dict[UUID, RtgAnchor] = {}
        self._data_objects: dict[UUID, RtgDataObject] = {}
        self._links: dict[UUID, RtgLink] = {}
        self._type_to_uuids: dict[str, set[UUID]] = {}
        self._type_to_kind: dict[str, str] = {}
        self._data_to_anchors: dict[UUID, set[UUID]] = {}
        self._anchor_to_data: dict[UUID, set[UUID]] = {}
        self._incident_links: dict[UUID, set[UUID]] = {}

    @classmethod
    def empty(cls) -> InMemoryRtgGraph:
        return cls()

    @classmethod
    def import_snapshot(cls, snapshot: RtgGraphSnapshot) -> InMemoryRtgGraph:
        graph = cls.empty()
        try:
            anchors = tuple(_anchor_from_snapshot(record) for record in snapshot.anchors)
            data_objects = tuple(
                _data_object_from_snapshot(record) for record in snapshot.data_objects
            )
            links = tuple(_link_from_snapshot(record) for record in snapshot.links)
            anchor_data_index = {
                _parse_uuid(anchor_uuid): tuple(_parse_uuid(data_uuid) for data_uuid in data_uuids)
                for anchor_uuid, data_uuids in snapshot.anchor_data_index.items()
            }
        except (AttributeError, TypeError, ValueError) as error:
            raise RtgGraphSnapshotInvalid(str(error)) from error

        _validate_unique_snapshot_uuids((*anchors, *data_objects, *links))

        for anchor in anchors:
            graph.put_anchor(anchor)
        for data_object in data_objects:
            data_uuid = _record_uuid(data_object)
            graph._validate_new_uuid(data_uuid, _DATA_KIND)
            graph._validate_type_for_kind(data_object.type, _DATA_KIND)
            graph._data_objects[data_uuid] = _copy_data_object(data_object)
            graph._add_type_index(data_object.type, _DATA_KIND, data_uuid)

        referenced_data: set[UUID] = set()
        for anchor_uuid, data_uuids in anchor_data_index.items():
            if anchor_uuid not in graph._anchors:
                raise RtgGraphReferenceInvalid(
                    f"anchor_data_index references missing anchor: {anchor_uuid}"
                )
            for data_uuid in data_uuids:
                if data_uuid not in graph._data_objects:
                    raise RtgGraphReferenceInvalid(
                        f"anchor_data_index references missing data object: {data_uuid}"
                    )
                graph._add_anchor_data_pair(anchor_uuid, data_uuid)
                referenced_data.add(data_uuid)

        missing_grounding = set(graph._data_objects) - referenced_data
        if missing_grounding:
            first = min(missing_grounding, key=str)
            raise RtgGraphReferenceInvalid(f"data object has no anchor index entry: {first}")

        for link in links:
            graph.put_link(link)

        return graph

    def export_snapshot(self) -> RtgGraphSnapshot:
        return RtgGraphSnapshot(
            anchors=tuple(
                _anchor_to_snapshot(anchor) for anchor in self._sorted(self._anchors.values())
            ),
            data_objects=tuple(
                _data_object_to_snapshot(data_object)
                for data_object in self._sorted(self._data_objects.values())
            ),
            links=tuple(_link_to_snapshot(link) for link in self._sorted(self._links.values())),
            anchor_data_index={
                str(anchor_uuid): tuple(str(data_uuid) for data_uuid in sorted(data_uuids, key=str))
                for anchor_uuid, data_uuids in sorted(
                    self._anchor_to_data.items(), key=lambda item: str(item[0])
                )
                if data_uuids
            },
        )

    def put_anchor(self, anchor: RtgAnchor) -> RtgAnchor:
        normalized = self._normalize_anchor(anchor)
        anchor_uuid = _record_uuid(normalized)
        self._validate_new_uuid(anchor_uuid, _ANCHOR_KIND)
        self._validate_type_for_kind(normalized.type, _ANCHOR_KIND, existing_uuid=anchor_uuid)

        previous = self._anchors.get(anchor_uuid)
        if previous is not None:
            self._remove_type_index(previous.type, _record_uuid(previous))
        self._anchors[anchor_uuid] = normalized
        self._add_type_index(normalized.type, _ANCHOR_KIND, anchor_uuid)
        self._anchor_to_data.setdefault(anchor_uuid, set())
        self._incident_links.setdefault(anchor_uuid, set())
        return _copy_anchor(normalized)

    def put_data_object(
        self,
        data_object: RtgDataObject,
        anchor_uuids: tuple[UuidInput, ...],
    ) -> RtgDataObject:
        normalized = self._normalize_data_object(data_object)
        data_uuid = _record_uuid(normalized)
        anchors = tuple(_parse_uuid(anchor_uuid) for anchor_uuid in anchor_uuids)
        if not anchors:
            raise RtgGraphAnchorNotFound("data objects must be indexed to at least one anchor")
        for anchor_uuid in anchors:
            if anchor_uuid not in self._anchors:
                raise RtgGraphAnchorNotFound(str(anchor_uuid))

        self._validate_new_uuid(data_uuid, _DATA_KIND)
        self._validate_type_for_kind(normalized.type, _DATA_KIND, existing_uuid=data_uuid)

        previous = self._data_objects.get(data_uuid)
        if previous is not None:
            self._remove_type_index(previous.type, _record_uuid(previous))
            for anchor_uuid in tuple(self._data_to_anchors.get(data_uuid, ())):
                self._remove_anchor_data_pair(anchor_uuid, data_uuid)

        self._data_objects[data_uuid] = normalized
        self._add_type_index(normalized.type, _DATA_KIND, data_uuid)
        self._incident_links.setdefault(data_uuid, set())
        for anchor_uuid in anchors:
            self._add_anchor_data_pair(anchor_uuid, data_uuid)
        return _copy_data_object(normalized)

    def put_link(self, link: RtgLink) -> RtgLink:
        normalized = self._normalize_link(link)
        link_uuid = _record_uuid(normalized)
        self._validate_new_uuid(link_uuid, _LINK_KIND)
        self._validate_type_for_kind(normalized.type, _LINK_KIND, existing_uuid=link_uuid)
        self._validate_endpoint(normalized.source_uuid)
        self._validate_endpoint(normalized.target_uuid)

        previous = self._links.get(link_uuid)
        if previous is not None:
            previous_uuid = _record_uuid(previous)
            self._remove_type_index(previous.type, previous_uuid)
            self._remove_incident_link(previous.source_uuid, previous_uuid)
            self._remove_incident_link(previous.target_uuid, previous_uuid)

        self._links[link_uuid] = normalized
        self._add_type_index(normalized.type, _LINK_KIND, link_uuid)
        self._add_incident_link(normalized.source_uuid, link_uuid)
        self._add_incident_link(normalized.target_uuid, link_uuid)
        return _copy_link(normalized)

    def associate_data(self, anchor_uuid: UuidInput, data_uuid: UuidInput) -> None:
        anchor = _parse_uuid(anchor_uuid)
        data = _parse_uuid(data_uuid)
        if anchor not in self._anchors:
            raise RtgGraphAnchorNotFound(str(anchor))
        if data not in self._data_objects:
            raise RtgGraphDataObjectNotFound(str(data))
        self._add_anchor_data_pair(anchor, data)

    def dissociate_data(self, anchor_uuid: UuidInput, data_uuid: UuidInput) -> RtgGraphDeleteResult:
        anchor = _parse_uuid(anchor_uuid)
        data = _parse_uuid(data_uuid)
        if anchor not in self._anchors:
            raise RtgGraphAnchorNotFound(str(anchor))
        if data not in self._data_objects:
            raise RtgGraphDataObjectNotFound(str(data))
        if data not in self._anchor_to_data.get(anchor, set()):
            raise RtgGraphAnchorDataIndexEntryNotFound(f"{anchor} -> {data}")

        self._remove_anchor_data_pair(anchor, data)
        removed_pairs = [(anchor, data)]
        deleted_data: list[RtgDataObject] = []
        deleted_links: list[RtgLink] = []
        if not self._data_to_anchors.get(data):
            data_object, links = self._delete_data_object_record(data)
            deleted_data.append(data_object)
            deleted_links.extend(links)

        return _delete_result(
            deleted_data_objects=deleted_data,
            deleted_links=deleted_links,
            removed_anchor_data_pairs=removed_pairs,
        )

    def delete_anchor(self, anchor_uuid: UuidInput) -> RtgGraphDeleteResult:
        anchor = _parse_uuid(anchor_uuid)
        if anchor not in self._anchors:
            raise RtgGraphAnchorNotFound(str(anchor))

        deleted_links = self._delete_incident_links(anchor)
        removed_pairs: list[tuple[UUID, UUID]] = []
        deleted_data: list[RtgDataObject] = []

        for data in tuple(self._anchor_to_data.get(anchor, set())):
            self._remove_anchor_data_pair(anchor, data)
            removed_pairs.append((anchor, data))
            if not self._data_to_anchors.get(data):
                data_object, cascaded_links = self._delete_data_object_record(data)
                deleted_data.append(data_object)
                deleted_links.extend(cascaded_links)

        anchor_record = self._anchors.pop(anchor)
        self._remove_type_index(anchor_record.type, _record_uuid(anchor_record))
        self._anchor_to_data.pop(anchor, None)
        self._incident_links.pop(anchor, None)

        return _delete_result(
            deleted_anchors=[anchor_record],
            deleted_data_objects=deleted_data,
            deleted_links=deleted_links,
            removed_anchor_data_pairs=removed_pairs,
        )

    def delete_data_object(self, data_uuid: UuidInput) -> RtgGraphDeleteResult:
        data = _parse_uuid(data_uuid)
        if data not in self._data_objects:
            raise RtgGraphDataObjectNotFound(str(data))

        removed_pairs = [(anchor, data) for anchor in tuple(self._data_to_anchors.get(data, set()))]
        for anchor, _ in removed_pairs:
            self._remove_anchor_data_pair(anchor, data)
        data_object, deleted_links = self._delete_data_object_record(data)

        return _delete_result(
            deleted_data_objects=[data_object],
            deleted_links=deleted_links,
            removed_anchor_data_pairs=removed_pairs,
        )

    def delete_link(self, link_uuid: UuidInput) -> RtgGraphDeleteResult:
        link = _parse_uuid(link_uuid)
        if link not in self._links:
            raise RtgGraphLinkNotFound(str(link))
        deleted_link = self._delete_link_record(link)
        return _delete_result(deleted_links=[deleted_link])

    def preview_delete_anchor(self, anchor_uuid: UuidInput) -> RtgGraphDeleteResult:
        anchor = _parse_uuid(anchor_uuid)
        if anchor not in self._anchors:
            raise RtgGraphAnchorNotFound(str(anchor))
        return self._preview_delete_anchor(anchor)

    def preview_delete_data_object(self, data_uuid: UuidInput) -> RtgGraphDeleteResult:
        data = _parse_uuid(data_uuid)
        if data not in self._data_objects:
            raise RtgGraphDataObjectNotFound(str(data))
        return self._preview_delete_data_object(data)

    def preview_dissociate_data(
        self, anchor_uuid: UuidInput, data_uuid: UuidInput
    ) -> RtgGraphDeleteResult:
        anchor = _parse_uuid(anchor_uuid)
        data = _parse_uuid(data_uuid)
        if anchor not in self._anchors:
            raise RtgGraphAnchorNotFound(str(anchor))
        if data not in self._data_objects:
            raise RtgGraphDataObjectNotFound(str(data))
        if data not in self._anchor_to_data.get(anchor, set()):
            raise RtgGraphAnchorDataIndexEntryNotFound(f"{anchor} -> {data}")
        return self._preview_dissociate_data(anchor, data)

    def get_object(self, object_uuid: UuidInput) -> RtgObject:
        uuid_value = _parse_uuid(object_uuid)
        if uuid_value in self._anchors:
            return _copy_anchor(self._anchors[uuid_value])
        if uuid_value in self._data_objects:
            return _copy_data_object(self._data_objects[uuid_value])
        if uuid_value in self._links:
            return _copy_link(self._links[uuid_value])
        raise RtgGraphObjectNotFound(str(uuid_value))

    def list_by_type(self, object_type: str) -> RtgObjectList:
        normalized_type = _validate_type(object_type)
        objects = [
            self._object_for_uuid(uuid_value)
            for uuid_value in self._type_to_uuids.get(normalized_type, set())
        ]
        return RtgObjectList(objects=tuple(self._copy_object(obj) for obj in self._sorted(objects)))

    def list_anchor_data(self, anchor_uuid: UuidInput) -> RtgDataObjectList:
        anchor = _parse_uuid(anchor_uuid)
        if anchor not in self._anchors:
            raise RtgGraphAnchorNotFound(str(anchor))
        data = [
            self._data_objects[data_uuid] for data_uuid in self._anchor_to_data.get(anchor, set())
        ]
        return RtgDataObjectList(
            data_objects=tuple(_copy_data_object(item) for item in self._sorted(data))
        )

    def list_data_anchors(self, data_uuid: UuidInput) -> RtgAnchorList:
        data = _parse_uuid(data_uuid)
        if data not in self._data_objects:
            raise RtgGraphDataObjectNotFound(str(data))
        anchors = [
            self._anchors[anchor_uuid] for anchor_uuid in self._data_to_anchors.get(data, set())
        ]
        return RtgAnchorList(anchors=tuple(_copy_anchor(item) for item in self._sorted(anchors)))

    def list_incident_links(self, object_uuid: UuidInput, direction: str = "both") -> RtgLinkList:
        uuid_value = _parse_uuid(object_uuid)
        if uuid_value not in self._anchors and uuid_value not in self._data_objects:
            raise RtgGraphObjectNotFound(str(uuid_value))
        if direction not in _VALID_DIRECTIONS:
            raise RtgGraphReferenceInvalid(f"invalid link direction: {direction}")

        links = []
        for link_uuid in self._incident_links.get(uuid_value, set()):
            link = self._links[link_uuid]
            if direction == "source" and link.source_uuid != uuid_value:
                continue
            if direction == "target" and link.target_uuid != uuid_value:
                continue
            links.append(link)
        return RtgLinkList(links=tuple(_copy_link(link) for link in self._sorted(links)))

    def count_by_type(self, kind: str | None = None, live: bool | None = None) -> RtgTypeCountList:
        if kind is not None and kind not in _VALID_KINDS:
            raise RtgGraphTypeInvalid(f"invalid object kind: {kind}")

        counts: dict[tuple[str, str], int] = {}
        for object_kind, objects in (
            (_ANCHOR_KIND, self._anchors.values()),
            (_DATA_KIND, self._data_objects.values()),
            (_LINK_KIND, self._links.values()),
        ):
            if kind is not None and object_kind != kind:
                continue
            for obj in objects:
                if live is not None and obj.system["live"] != live:
                    continue
                key = (obj.type, object_kind)
                counts[key] = counts.get(key, 0) + 1

        return RtgTypeCountList(
            counts=tuple(
                RtgTypeCount(type=object_type, kind=object_kind, live=live, count=count)
                for (object_type, object_kind), count in sorted(
                    counts.items(), key=lambda item: (item[0][1], item[0][0])
                )
            )
        )

    def _normalize_anchor(self, anchor: RtgAnchor) -> RtgAnchor:
        return RtgAnchor(
            uuid=self._resolve_write_uuid(anchor.uuid),
            type=_validate_type(anchor.type),
            display_name=_normalize_display_name(anchor.display_name),
            system=_normalize_system(anchor.system),
        )

    def _normalize_data_object(self, data_object: RtgDataObject) -> RtgDataObject:
        return RtgDataObject(
            uuid=self._resolve_write_uuid(data_object.uuid),
            type=_validate_type(data_object.type),
            properties=_validate_json_object(data_object.properties, RtgGraphJsonValueInvalid),
            system=_normalize_system(data_object.system),
        )

    def _normalize_link(self, link: RtgLink) -> RtgLink:
        return RtgLink(
            uuid=self._resolve_write_uuid(link.uuid),
            type=_validate_type(link.type),
            source_uuid=_parse_uuid(link.source_uuid),
            target_uuid=_parse_uuid(link.target_uuid),
            system=_normalize_system(link.system),
        )

    def _resolve_write_uuid(self, value: UuidInput | None) -> UUID:
        if value is None:
            return self._generate_uuid()
        return _parse_uuid(value)

    def _generate_uuid(self) -> UUID:
        while True:
            uuid_value = uuid4()
            if (
                uuid_value not in self._anchors
                and uuid_value not in self._data_objects
                and uuid_value not in self._links
            ):
                return uuid_value

    def _validate_new_uuid(self, uuid_value: UUID, kind: str) -> None:
        if kind != _ANCHOR_KIND and uuid_value in self._anchors:
            raise RtgGraphUuidConflict(str(uuid_value))
        if kind != _DATA_KIND and uuid_value in self._data_objects:
            raise RtgGraphUuidConflict(str(uuid_value))
        if kind != _LINK_KIND and uuid_value in self._links:
            raise RtgGraphUuidConflict(str(uuid_value))

    def _validate_type_for_kind(
        self,
        object_type: str,
        kind: str,
        *,
        existing_uuid: UUID | None = None,
    ) -> None:
        existing_kind = self._type_to_kind.get(object_type)
        if existing_kind is not None and existing_kind != kind:
            raise RtgGraphTypeKindConflict(f"type {object_type!r} belongs to {existing_kind}")

        if existing_uuid is not None and object_type in self._type_to_uuids:
            other_uuids = self._type_to_uuids[object_type] - {existing_uuid}
            if other_uuids and existing_kind != kind:
                raise RtgGraphTypeKindConflict(
                    f"type {object_type!r} belongs to another object kind"
                )

    def _validate_endpoint(self, uuid_value: UUID) -> None:
        if uuid_value in self._links:
            raise RtgGraphEndpointNotFound(f"links cannot be endpoints: {uuid_value}")
        if uuid_value not in self._anchors and uuid_value not in self._data_objects:
            raise RtgGraphEndpointNotFound(str(uuid_value))

    def _add_type_index(self, object_type: str, kind: str, uuid_value: UUID) -> None:
        self._type_to_uuids.setdefault(object_type, set()).add(uuid_value)
        self._type_to_kind[object_type] = kind

    def _remove_type_index(self, object_type: str, uuid_value: UUID) -> None:
        uuids = self._type_to_uuids.get(object_type)
        if uuids is None:
            return
        uuids.discard(uuid_value)
        if not uuids:
            self._type_to_uuids.pop(object_type, None)
            self._type_to_kind.pop(object_type, None)

    def _add_anchor_data_pair(self, anchor: UUID, data: UUID) -> None:
        self._anchor_to_data.setdefault(anchor, set()).add(data)
        self._data_to_anchors.setdefault(data, set()).add(anchor)

    def _remove_anchor_data_pair(self, anchor: UUID, data: UUID) -> None:
        data_set = self._anchor_to_data.get(anchor)
        if data_set is not None:
            data_set.discard(data)
        anchor_set = self._data_to_anchors.get(data)
        if anchor_set is not None:
            anchor_set.discard(anchor)

    def _add_incident_link(self, endpoint: UUID, link: UUID) -> None:
        self._incident_links.setdefault(endpoint, set()).add(link)

    def _remove_incident_link(self, endpoint: UUID, link: UUID) -> None:
        links = self._incident_links.get(endpoint)
        if links is not None:
            links.discard(link)

    def _delete_incident_links(self, object_uuid: UUID) -> list[RtgLink]:
        deleted = []
        for link_uuid in tuple(self._incident_links.get(object_uuid, set())):
            if link_uuid in self._links:
                deleted.append(self._delete_link_record(link_uuid))
        return deleted

    def _delete_data_object_record(self, data_uuid: UUID) -> tuple[RtgDataObject, list[RtgLink]]:
        deleted_links = self._delete_incident_links(data_uuid)
        data_object = self._data_objects.pop(data_uuid)
        self._remove_type_index(data_object.type, _record_uuid(data_object))
        self._data_to_anchors.pop(data_uuid, None)
        self._incident_links.pop(data_uuid, None)
        return data_object, deleted_links

    def _delete_link_record(self, link_uuid: UUID) -> RtgLink:
        link = self._links.pop(link_uuid)
        removed_uuid = _record_uuid(link)
        self._remove_type_index(link.type, removed_uuid)
        self._remove_incident_link(link.source_uuid, removed_uuid)
        self._remove_incident_link(link.target_uuid, removed_uuid)
        return link

    def _preview_delete_anchor(self, anchor: UUID) -> RtgGraphDeleteResult:
        deleted_link_uuids = set(self._incident_links.get(anchor, set()))
        removed_pairs: list[tuple[UUID, UUID]] = []
        deleted_data: list[RtgDataObject] = []

        for data in self._anchor_to_data.get(anchor, set()):
            removed_pairs.append((anchor, data))
            if not (self._data_to_anchors.get(data, set()) - {anchor}):
                deleted_data.append(self._data_objects[data])
                deleted_link_uuids.update(self._incident_links.get(data, set()))

        return _delete_result(
            deleted_anchors=[self._anchors[anchor]],
            deleted_data_objects=deleted_data,
            deleted_links=(self._links[link_uuid] for link_uuid in deleted_link_uuids),
            removed_anchor_data_pairs=removed_pairs,
        )

    def _preview_delete_data_object(self, data: UUID) -> RtgGraphDeleteResult:
        removed_pairs = [(anchor, data) for anchor in self._data_to_anchors.get(data, set())]
        deleted_link_uuids = set(self._incident_links.get(data, set()))
        return _delete_result(
            deleted_data_objects=[self._data_objects[data]],
            deleted_links=(self._links[link_uuid] for link_uuid in deleted_link_uuids),
            removed_anchor_data_pairs=removed_pairs,
        )

    def _preview_dissociate_data(self, anchor: UUID, data: UUID) -> RtgGraphDeleteResult:
        removed_pairs = [(anchor, data)]
        if self._data_to_anchors.get(data, set()) - {anchor}:
            return _delete_result(removed_anchor_data_pairs=removed_pairs)
        deleted_link_uuids = set(self._incident_links.get(data, set()))
        return _delete_result(
            deleted_data_objects=[self._data_objects[data]],
            deleted_links=(self._links[link_uuid] for link_uuid in deleted_link_uuids),
            removed_anchor_data_pairs=removed_pairs,
        )

    def _object_for_uuid(self, uuid_value: UUID) -> RtgObject:
        if uuid_value in self._anchors:
            return self._anchors[uuid_value]
        if uuid_value in self._data_objects:
            return self._data_objects[uuid_value]
        return self._links[uuid_value]

    def _copy_object(self, obj: RtgObject) -> RtgObject:
        if isinstance(obj, RtgAnchor):
            return _copy_anchor(obj)
        if isinstance(obj, RtgDataObject):
            return _copy_data_object(obj)
        return _copy_link(obj)

    @staticmethod
    def _sorted[T: RtgObject](objects: Iterable[T]) -> tuple[T, ...]:
        return tuple(sorted(objects, key=lambda obj: str(_record_uuid(obj))))


def _parse_uuid(value: UuidInput) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise RtgGraphUuidInvalid(str(value)) from error


def _snapshot_uuid(value: JsonValue) -> UUID:
    if not isinstance(value, str):
        raise RtgGraphUuidInvalid(str(value))
    return _parse_uuid(value)


def _snapshot_type(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise RtgGraphTypeInvalid("type must be a string")
    return _validate_type(value)


def _validate_type(value: str) -> str:
    if not isinstance(value, str):
        raise RtgGraphTypeInvalid("type must be a string")
    if value == "" or value != value.strip() or any(ord(character) < 32 for character in value):
        raise RtgGraphTypeInvalid(f"invalid type: {value!r}")
    return value


def _normalize_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RtgGraphSystemValueInvalid("display_name must be a string when supplied")
    return value


def _normalize_system(value: JsonObject) -> JsonObject:
    system = _validate_json_object(value, RtgGraphSystemValueInvalid)
    live = system.get("live", True)
    if not isinstance(live, bool):
        raise RtgGraphSystemValueInvalid("system.live must be boolean")
    system["live"] = live
    return system


def _validate_json_object(
    value: JsonObject,
    error_type: type[RtgGraphJsonValueInvalid] | type[RtgGraphSystemValueInvalid],
) -> JsonObject:
    if not isinstance(value, dict):
        raise error_type("value must be a JSON object")
    copied = copy.deepcopy(value)
    _validate_json_value(copied, error_type)
    return copied


def _validate_json_value(
    value: JsonValue,
    error_type: type[RtgGraphJsonValueInvalid] | type[RtgGraphSystemValueInvalid],
) -> None:
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise error_type("JSON object keys must be strings")
        for item in value.values():
            _validate_json_value(item, error_type)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, error_type)
        return
    if value is None or isinstance(value, str | int | float | bool):
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise error_type(str(error)) from error
        return
    raise error_type(f"value is not JSON serializable: {type(value).__name__}")


def _anchor_from_snapshot(record: JsonObject) -> RtgAnchor:
    try:
        return RtgAnchor(
            uuid=_snapshot_uuid(record["uuid"]),
            type=_snapshot_type(record["type"]),
            display_name=_snapshot_display_name(record),
            system=_snapshot_system(record),
        )
    except KeyError as error:
        raise RtgGraphSnapshotInvalid(f"anchor missing field: {error}") from error


def _data_object_from_snapshot(record: JsonObject) -> RtgDataObject:
    try:
        return RtgDataObject(
            uuid=_snapshot_uuid(record["uuid"]),
            type=_snapshot_type(record["type"]),
            properties=_snapshot_json_object(record["properties"]),
            system=_snapshot_system(record),
        )
    except KeyError as error:
        raise RtgGraphSnapshotInvalid(f"data object missing field: {error}") from error


def _link_from_snapshot(record: JsonObject) -> RtgLink:
    try:
        return RtgLink(
            uuid=_snapshot_uuid(record["uuid"]),
            type=_snapshot_type(record["type"]),
            source_uuid=_snapshot_uuid(record["source_uuid"]),
            target_uuid=_snapshot_uuid(record["target_uuid"]),
            system=_snapshot_system(record),
        )
    except KeyError as error:
        raise RtgGraphSnapshotInvalid(f"link missing field: {error}") from error


def _snapshot_system(record: JsonObject) -> JsonObject:
    system = record.get("system", {})
    if not isinstance(system, dict):
        raise RtgGraphSystemValueInvalid("snapshot system must be an object")
    return _normalize_system(system)


def _snapshot_display_name(record: JsonObject) -> str | None:
    display_name = record.get("display_name")
    if display_name is None:
        return None
    if not isinstance(display_name, str):
        raise RtgGraphSystemValueInvalid("snapshot display_name must be a string")
    return display_name


def _snapshot_json_object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise RtgGraphJsonValueInvalid("snapshot value must be an object")
    return _validate_json_object(value, RtgGraphJsonValueInvalid)


def _validate_unique_snapshot_uuids(objects: Iterable[RtgObject]) -> None:
    seen: set[UUID] = set()
    for obj in objects:
        obj_uuid = _record_uuid(obj)
        if obj_uuid in seen:
            raise RtgGraphUuidConflict(str(obj_uuid))
        seen.add(obj_uuid)


def _anchor_to_snapshot(anchor: RtgAnchor) -> JsonObject:
    snapshot = {
        "uuid": str(_record_uuid(anchor)),
        "type": anchor.type,
        "system": copy.deepcopy(anchor.system),
    }
    if anchor.display_name is not None:
        snapshot["display_name"] = anchor.display_name
    return snapshot


def _data_object_to_snapshot(data_object: RtgDataObject) -> JsonObject:
    return {
        "uuid": str(_record_uuid(data_object)),
        "type": data_object.type,
        "properties": copy.deepcopy(data_object.properties),
        "system": copy.deepcopy(data_object.system),
    }


def _link_to_snapshot(link: RtgLink) -> JsonObject:
    return {
        "uuid": str(_record_uuid(link)),
        "type": link.type,
        "source_uuid": str(link.source_uuid),
        "target_uuid": str(link.target_uuid),
        "system": copy.deepcopy(link.system),
    }


def _copy_anchor(anchor: RtgAnchor) -> RtgAnchor:
    return RtgAnchor(
        uuid=_record_uuid(anchor),
        type=anchor.type,
        display_name=anchor.display_name,
        system=copy.deepcopy(anchor.system),
    )


def _copy_data_object(data_object: RtgDataObject) -> RtgDataObject:
    return RtgDataObject(
        uuid=_record_uuid(data_object),
        type=data_object.type,
        properties=copy.deepcopy(data_object.properties),
        system=copy.deepcopy(data_object.system),
    )


def _copy_link(link: RtgLink) -> RtgLink:
    return RtgLink(
        uuid=_record_uuid(link),
        type=link.type,
        source_uuid=link.source_uuid,
        target_uuid=link.target_uuid,
        system=copy.deepcopy(link.system),
    )


def _delete_result(
    *,
    deleted_anchors: Iterable[RtgAnchor] = (),
    deleted_data_objects: Iterable[RtgDataObject] = (),
    deleted_links: Iterable[RtgLink] = (),
    removed_anchor_data_pairs: Iterable[tuple[UUID, UUID]] = (),
) -> RtgGraphDeleteResult:
    return RtgGraphDeleteResult(
        deleted_anchors=tuple(
            _copy_anchor(anchor)
            for anchor in sorted(deleted_anchors, key=lambda item: str(_record_uuid(item)))
        ),
        deleted_data_objects=tuple(
            _copy_data_object(data_object)
            for data_object in sorted(
                deleted_data_objects, key=lambda item: str(_record_uuid(item))
            )
        ),
        deleted_links=tuple(
            _copy_link(link)
            for link in sorted(deleted_links, key=lambda item: str(_record_uuid(item)))
        ),
        removed_anchor_data_pairs=tuple(
            sorted(removed_anchor_data_pairs, key=lambda item: (str(item[0]), str(item[1])))
        ),
    )


def _record_uuid(obj: RtgObject) -> UUID:
    if obj.uuid is None:
        raise RtgGraphUuidInvalid("object UUID is absent")
    return obj.uuid
