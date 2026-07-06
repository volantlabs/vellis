from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type UuidInput = UUID | str


@dataclass(frozen=True, slots=True)
class RtgAnchor:
    uuid: UUID | None
    type: str
    display_name: str | None = None
    system: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgDataObject:
    uuid: UUID | None
    type: str
    properties: JsonObject = field(default_factory=dict)
    system: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgLink:
    uuid: UUID | None
    type: str
    source_uuid: UUID
    target_uuid: UUID
    system: JsonObject = field(default_factory=dict)


type RtgObject = RtgAnchor | RtgDataObject | RtgLink


@dataclass(frozen=True, slots=True)
class RtgObjectList:
    objects: tuple[RtgObject, ...]


@dataclass(frozen=True, slots=True)
class RtgAnchorList:
    anchors: tuple[RtgAnchor, ...]


@dataclass(frozen=True, slots=True)
class RtgDataObjectList:
    data_objects: tuple[RtgDataObject, ...]


@dataclass(frozen=True, slots=True)
class RtgLinkList:
    links: tuple[RtgLink, ...]


@dataclass(frozen=True, slots=True)
class RtgGraphDeleteResult:
    deleted_anchors: tuple[RtgAnchor, ...] = ()
    deleted_data_objects: tuple[RtgDataObject, ...] = ()
    deleted_links: tuple[RtgLink, ...] = ()
    removed_anchor_data_pairs: tuple[tuple[UUID, UUID], ...] = ()


@dataclass(frozen=True, slots=True)
class RtgGraphSnapshot:
    anchors: tuple[JsonObject, ...]
    data_objects: tuple[JsonObject, ...]
    links: tuple[JsonObject, ...]
    anchor_data_index: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class RtgTypeCount:
    type: str
    kind: str
    live: bool | None
    count: int


@dataclass(frozen=True, slots=True)
class RtgTypeCountList:
    counts: tuple[RtgTypeCount, ...]


class RtgGraphError(Exception):
    """Base class for Reified Type Graph errors."""


class RtgGraphSnapshotInvalid(RtgGraphError):
    """A graph snapshot is malformed or internally inconsistent."""


class RtgGraphUuidInvalid(RtgGraphError):
    """A supplied UUID value is not parseable as a UUID."""


class RtgGraphUuidConflict(RtgGraphError):
    """A UUID is already used by a different RTG object kind."""


class RtgGraphReferenceInvalid(RtgGraphError):
    """A snapshot reference points at an invalid or missing object."""


class RtgGraphTypeInvalid(RtgGraphError):
    """A type value is not a well-formed RTG type string."""


class RtgGraphTypeKindConflict(RtgGraphError):
    """A type is already assigned to another RTG object kind."""


class RtgGraphJsonValueInvalid(RtgGraphError):
    """A supplied JSON property store is not a valid JSON object."""


class RtgGraphSystemValueInvalid(RtgGraphError):
    """A supplied system property store is invalid."""


class RtgGraphAnchorNotFound(RtgGraphError):
    """The requested anchor does not exist."""


class RtgGraphDataObjectNotFound(RtgGraphError):
    """The requested data object does not exist."""


class RtgGraphLinkNotFound(RtgGraphError):
    """The requested link does not exist."""


class RtgGraphEndpointNotFound(RtgGraphError):
    """A link endpoint does not resolve to an anchor or data object."""


class RtgGraphAnchorDataIndexEntryNotFound(RtgGraphError):
    """The requested anchor-data index entry does not exist."""


class RtgGraphObjectNotFound(RtgGraphError):
    """The requested RTG object does not exist."""


class RtgGraph(Protocol):
    @classmethod
    def empty(cls) -> RtgGraph:
        """Create an empty in-memory RTG graph."""
        ...

    @classmethod
    def import_snapshot(cls, snapshot: RtgGraphSnapshot) -> RtgGraph:
        """Create an in-memory RTG graph from a snapshot."""
        ...

    def export_snapshot(self) -> RtgGraphSnapshot:
        """Export a JSON-serializable graph snapshot."""
        ...

    def put_anchor(self, anchor: RtgAnchor) -> RtgAnchor:
        """Create or fully replace an anchor."""
        ...

    def put_data_object(
        self,
        data_object: RtgDataObject,
        anchor_uuids: tuple[UuidInput, ...],
    ) -> RtgDataObject:
        """Create or fully replace a data object and its anchor index entries."""
        ...

    def put_link(self, link: RtgLink) -> RtgLink:
        """Create or fully replace a link."""
        ...

    def associate_data(self, anchor_uuid: UuidInput, data_uuid: UuidInput) -> None:
        """Add a direct anchor-data index entry."""
        ...

    def dissociate_data(self, anchor_uuid: UuidInput, data_uuid: UuidInput) -> RtgGraphDeleteResult:
        """Remove a direct anchor-data index entry."""
        ...

    def delete_anchor(self, anchor_uuid: UuidInput) -> RtgGraphDeleteResult:
        """Delete an anchor and cascade no-longer-grounded data objects."""
        ...

    def delete_data_object(self, data_uuid: UuidInput) -> RtgGraphDeleteResult:
        """Delete a data object without deleting associated anchors."""
        ...

    def delete_link(self, link_uuid: UuidInput) -> RtgGraphDeleteResult:
        """Delete a link."""
        ...

    def preview_delete_anchor(self, anchor_uuid: UuidInput) -> RtgGraphDeleteResult:
        """Preview an anchor delete without mutating graph state."""
        ...

    def preview_delete_data_object(self, data_uuid: UuidInput) -> RtgGraphDeleteResult:
        """Preview a data object delete without mutating graph state."""
        ...

    def preview_dissociate_data(
        self, anchor_uuid: UuidInput, data_uuid: UuidInput
    ) -> RtgGraphDeleteResult:
        """Preview a data dissociation without mutating graph state."""
        ...

    def get_object(self, object_uuid: UuidInput) -> RtgObject:
        """Get an anchor, data object, or link by UUID."""
        ...

    def list_by_type(self, object_type: str) -> RtgObjectList:
        """List RTG objects by type across the global type namespace."""
        ...

    def list_anchor_data(self, anchor_uuid: UuidInput) -> RtgDataObjectList:
        """List data objects indexed to an anchor."""
        ...

    def list_data_anchors(self, data_uuid: UuidInput) -> RtgAnchorList:
        """List anchors indexed to a data object."""
        ...

    def list_incident_links(self, object_uuid: UuidInput, direction: str = "both") -> RtgLinkList:
        """List incident links for an anchor or data object."""
        ...

    def count_by_type(self, kind: str | None = None, live: bool | None = None) -> RtgTypeCountList:
        """Count graph objects by type, optionally filtered by kind and live status."""
        ...
