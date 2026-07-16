from __future__ import annotations

import copy
from dataclasses import replace
from typing import cast
from uuid import UUID

from components.rtg.constraints.protocol import (
    RtgConstraintDefinition,
    RtgConstraintDefinitionList,
    RtgConstraintDeleteResult,
)
from components.rtg.graph.protocol import (
    RtgAnchor,
    RtgAnchorList,
    RtgDataObject,
    RtgDataObjectList,
    RtgGraphAnchorNotFound,
    RtgGraphDataObjectNotFound,
    RtgGraphDeleteResult,
    RtgGraphLinkNotFound,
    RtgGraphObjectNotFound,
    RtgLink,
    RtgObject,
    RtgObjectList,
    RtgTypeCount,
    RtgTypeCountList,
    UuidInput,
)
from components.rtg.migration.protocol import (
    JsonObject,
    RtgMigrationDeleteResult,
    RtgMigrationEvidence,
    RtgMigrationRecord,
    RtgMigrationRecordList,
    RtgMigrationStatusTransitionInvalid,
    migration_status_transition_allowed,
)
from components.rtg.schema.protocol import (
    RtgSchemaDefinition,
    RtgSchemaDefinitionList,
    RtgSchemaDeleteResult,
)


def _uuid(value: UuidInput) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _page[T](values: tuple[T, ...], offset: int, limit: int | None) -> tuple[T, ...]:
    return values[offset:] if limit is None else values[offset : offset + limit]


def _live(value: object) -> bool | None:
    system = getattr(value, "system", {})
    return system.get("live") if isinstance(system, dict) else None


class ValidationGraphProjection:
    """Invocation-local graph view assembled from public targeted-read results."""

    def __init__(
        self,
        objects: tuple[RtgObject, ...],
        anchor_data: dict[UUID, set[UUID]],
    ) -> None:
        self._objects = {self._id(item): copy.deepcopy(item) for item in objects}
        self._anchor_data = {key: set(value) for key, value in anchor_data.items()}

    def clone_for_validation(self) -> ValidationGraphProjection:
        return ValidationGraphProjection(tuple(self._objects.values()), self._anchor_data)

    @staticmethod
    def _id(value: RtgObject) -> UUID:
        if value.uuid is None:
            raise ValueError("projected graph objects require UUIDs")
        return value.uuid

    def get_object(self, object_uuid: UuidInput) -> RtgObject:
        key = _uuid(object_uuid)
        try:
            return copy.deepcopy(self._objects[key])
        except KeyError as error:
            raise RtgGraphObjectNotFound(str(key)) from error

    def list_by_type(
        self, object_type: str, offset: int = 0, limit: int | None = None
    ) -> RtgObjectList:
        values = tuple(
            copy.deepcopy(item)
            for item in sorted(self._objects.values(), key=lambda item: str(self._id(item)))
            if item.type == object_type
        )
        return RtgObjectList(_page(values, offset, limit))

    def list_anchor_data(
        self, anchor_uuid: UuidInput, offset: int = 0, limit: int | None = None
    ) -> RtgDataObjectList:
        values = tuple(
            copy.deepcopy(cast(RtgDataObject, self._objects[item]))
            for item in sorted(self._anchor_data.get(_uuid(anchor_uuid), set()), key=str)
            if isinstance(self._objects.get(item), RtgDataObject)
        )
        return RtgDataObjectList(_page(values, offset, limit))

    def list_data_anchors(
        self, data_uuid: UuidInput, offset: int = 0, limit: int | None = None
    ) -> RtgAnchorList:
        data = _uuid(data_uuid)
        values = tuple(
            copy.deepcopy(cast(RtgAnchor, self._objects[anchor]))
            for anchor in sorted(
                (key for key, items in self._anchor_data.items() if data in items), key=str
            )
            if isinstance(self._objects.get(anchor), RtgAnchor)
        )
        return RtgAnchorList(_page(values, offset, limit))

    def count_by_type(self, kind: str | None = None, live: bool | None = None) -> RtgTypeCountList:
        counts: dict[tuple[str, str, bool | None], int] = {}
        for item in self._objects.values():
            item_kind = (
                "anchor"
                if isinstance(item, RtgAnchor)
                else "data_object"
                if isinstance(item, RtgDataObject)
                else "link"
            )
            item_live = _live(item)
            if (kind is None or item_kind == kind) and (live is None or item_live == live):
                key = (item.type, item_kind, item_live)
                counts[key] = counts.get(key, 0) + 1
        return RtgTypeCountList(
            tuple(RtgTypeCount(*key, count) for key, count in sorted(counts.items()))
        )

    def put_anchor(self, anchor: RtgAnchor) -> RtgAnchor:
        self._objects[self._id(anchor)] = copy.deepcopy(anchor)
        self._anchor_data.setdefault(self._id(anchor), set())
        return copy.deepcopy(anchor)

    def put_data_object(
        self, data_object: RtgDataObject, anchor_uuids: tuple[UuidInput, ...]
    ) -> RtgDataObject:
        data = self._id(data_object)
        self._objects[data] = copy.deepcopy(data_object)
        for values in self._anchor_data.values():
            values.discard(data)
        for anchor in anchor_uuids:
            self._anchor_data.setdefault(_uuid(anchor), set()).add(data)
        return copy.deepcopy(data_object)

    def put_link(self, link: RtgLink) -> RtgLink:
        self._objects[self._id(link)] = copy.deepcopy(link)
        return copy.deepcopy(link)

    def associate_data(self, anchor_uuid: UuidInput, data_uuid: UuidInput) -> None:
        self._anchor_data.setdefault(_uuid(anchor_uuid), set()).add(_uuid(data_uuid))

    def dissociate_data(self, anchor_uuid: UuidInput, data_uuid: UuidInput) -> RtgGraphDeleteResult:
        anchor, data = _uuid(anchor_uuid), _uuid(data_uuid)
        self._anchor_data.setdefault(anchor, set()).discard(data)
        if not any(data in values for values in self._anchor_data.values()):
            return self.delete_data_object(data)
        return RtgGraphDeleteResult(removed_anchor_data_pairs=((anchor, data),))

    def delete_link(self, link_uuid: UuidInput) -> RtgGraphDeleteResult:
        key = _uuid(link_uuid)
        try:
            deleted = self._objects.pop(key)
        except KeyError as error:
            raise RtgGraphLinkNotFound(str(key)) from error
        return RtgGraphDeleteResult(deleted_links=(copy.deepcopy(deleted),))  # type: ignore[arg-type]

    def delete_data_object(self, data_uuid: UuidInput) -> RtgGraphDeleteResult:
        data = _uuid(data_uuid)
        try:
            deleted = self._objects.pop(data)
        except KeyError as error:
            raise RtgGraphDataObjectNotFound(str(data)) from error
        removed = []
        for anchor, values in self._anchor_data.items():
            if data in values:
                values.remove(data)
                removed.append((anchor, data))
        links = self._delete_incident(data)
        return RtgGraphDeleteResult(
            deleted_data_objects=(copy.deepcopy(deleted),),  # type: ignore[arg-type]
            deleted_links=links,
            removed_anchor_data_pairs=tuple(removed),
        )

    def delete_anchor(self, anchor_uuid: UuidInput) -> RtgGraphDeleteResult:
        anchor = _uuid(anchor_uuid)
        try:
            deleted = self._objects.pop(anchor)
        except KeyError as error:
            raise RtgGraphAnchorNotFound(str(anchor)) from error
        data_values = tuple(self._anchor_data.pop(anchor, set()))
        deleted_data: list[RtgDataObject] = []
        deleted_links = list(self._delete_incident(anchor))
        for data in data_values:
            if not any(data in values for values in self._anchor_data.values()):
                result = self.delete_data_object(data)
                deleted_data.extend(result.deleted_data_objects)
                deleted_links.extend(result.deleted_links)
        return RtgGraphDeleteResult(
            deleted_anchors=(copy.deepcopy(deleted),),  # type: ignore[arg-type]
            deleted_data_objects=tuple(deleted_data),
            deleted_links=tuple(deleted_links),
            removed_anchor_data_pairs=tuple((anchor, data) for data in data_values),
        )

    def _delete_incident(self, object_uuid: UUID) -> tuple[RtgLink, ...]:
        deleted = []
        for key, item in tuple(self._objects.items()):
            if isinstance(item, RtgLink) and object_uuid in {item.source_uuid, item.target_uuid}:
                deleted.append(copy.deepcopy(self._objects.pop(key)))
        return tuple(deleted)


class ValidationSchemaProjection:
    def __init__(self, values: tuple[RtgSchemaDefinition, ...]) -> None:
        self._values = {self._id(value): copy.deepcopy(value) for value in values}

    @staticmethod
    def _id(value: RtgSchemaDefinition) -> UUID:
        if value.uuid is None:
            raise ValueError("projected schema definitions require UUIDs")
        return value.uuid

    def clone_for_validation(self) -> ValidationSchemaProjection:
        return ValidationSchemaProjection(tuple(self._values.values()))

    def put_definition(self, value: RtgSchemaDefinition) -> RtgSchemaDefinition:
        self._values[self._id(value)] = copy.deepcopy(value)
        return copy.deepcopy(value)

    def get_definition(self, value: UuidInput) -> RtgSchemaDefinition:
        return copy.deepcopy(self._values[_uuid(value)])

    def list_definitions(
        self,
        kind: str | None = None,
        live: bool | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> RtgSchemaDefinitionList:
        values = tuple(
            copy.deepcopy(item)
            for item in sorted(self._values.values(), key=lambda item: str(self._id(item)))
            if (kind is None or item.kind == kind) and (live is None or _live(item) == live)
        )
        return RtgSchemaDefinitionList(_page(values, offset, limit))

    def list_definitions_by_type_key(
        self,
        schema_type_key: str,
        kind: str | None = None,
        live: bool | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> RtgSchemaDefinitionList:
        values = tuple(
            item
            for item in self.list_definitions(kind, live).definitions
            if item.type_key == schema_type_key
        )
        return RtgSchemaDefinitionList(_page(values, offset, limit))

    def delete_definition(self, value: UuidInput) -> RtgSchemaDeleteResult:
        return RtgSchemaDeleteResult(copy.deepcopy(self._values.pop(_uuid(value))))


class ValidationConstraintProjection:
    def __init__(self, values: tuple[RtgConstraintDefinition, ...]) -> None:
        self._values = {self._id(value): copy.deepcopy(value) for value in values}

    @staticmethod
    def _id(value: RtgConstraintDefinition) -> UUID:
        if value.uuid is None:
            raise ValueError("projected constraints require UUIDs")
        return value.uuid

    def clone_for_validation(self) -> ValidationConstraintProjection:
        return ValidationConstraintProjection(tuple(self._values.values()))

    def put_constraint(self, value: RtgConstraintDefinition) -> RtgConstraintDefinition:
        self._values[self._id(value)] = copy.deepcopy(value)
        return copy.deepcopy(value)

    def get_constraint(self, value: UuidInput) -> RtgConstraintDefinition:
        return copy.deepcopy(self._values[_uuid(value)])

    def list_constraints(
        self,
        kind: str | None = None,
        live: bool | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> RtgConstraintDefinitionList:
        values = tuple(
            copy.deepcopy(item)
            for item in sorted(self._values.values(), key=lambda item: str(self._id(item)))
            if (kind is None or item.kind == kind) and (live is None or _live(item) == live)
        )
        return RtgConstraintDefinitionList(_page(values, offset, limit))

    def delete_constraint(self, value: UuidInput) -> RtgConstraintDeleteResult:
        return RtgConstraintDeleteResult(copy.deepcopy(self._values.pop(_uuid(value))))


class ValidationMigrationProjection:
    def __init__(self, values: tuple[RtgMigrationRecord, ...]) -> None:
        self._values = {self._id(value): copy.deepcopy(value) for value in values}

    @staticmethod
    def _id(value: RtgMigrationRecord) -> str:
        if value.migration_id is None:
            raise ValueError("projected migrations require IDs")
        return value.migration_id

    def clone_for_validation(self) -> ValidationMigrationProjection:
        return ValidationMigrationProjection(tuple(self._values.values()))

    def put_migration(self, value: RtgMigrationRecord) -> RtgMigrationRecord:
        key = self._id(value)
        current = self._values.get(key)
        if current is not None and value.status != current.status:
            self._require_transition(current.status, value.status)
        self._values[key] = copy.deepcopy(value)
        return copy.deepcopy(value)

    def get_migration(self, value: str) -> RtgMigrationRecord:
        return copy.deepcopy(self._values[value])

    def list_migrations(
        self, status: str | None = None, offset: int = 0, limit: int | None = None
    ) -> RtgMigrationRecordList:
        values = tuple(
            copy.deepcopy(item)
            for item in sorted(self._values.values(), key=self._id)
            if status is None or item.status == status
        )
        page = _page(values, offset, limit)
        next_offset = offset + len(page) if offset + len(page) < len(values) else None
        return RtgMigrationRecordList(page, len(values), next_offset)

    def set_status(
        self, migration_id: str, status: str, status_metadata: JsonObject | None = None
    ) -> RtgMigrationRecord:
        current = self._values[migration_id]
        self._require_transition(current.status, status)
        metadata = copy.deepcopy(current.metadata)
        metadata["status_metadata"] = copy.deepcopy(status_metadata or {})
        updated = replace(current, status=status, metadata=metadata)
        self._values[migration_id] = updated
        return copy.deepcopy(updated)

    def add_evidence(self, migration_id: str, evidence: RtgMigrationEvidence) -> RtgMigrationRecord:
        current = self._values[migration_id]
        updated = replace(current, evidence=(*current.evidence, copy.deepcopy(evidence)))
        self._values[migration_id] = updated
        return copy.deepcopy(updated)

    def delete_migration(self, migration_id: str) -> RtgMigrationDeleteResult:
        return RtgMigrationDeleteResult(copy.deepcopy(self._values.pop(migration_id)))

    @staticmethod
    def _require_transition(current: str, requested: str) -> None:
        if not migration_status_transition_allowed(current, requested):
            raise RtgMigrationStatusTransitionInvalid(f"{current} -> {requested}")
