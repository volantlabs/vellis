"""Identity-bearing graph objects and canonical graph equality.

Realizes ``RTG::'Graph Object'``, ``RTG::Anchor``, ``RTG::'Associated Data Object'``,
``RTG::Link``, ``RTG::Graph``, and ``RTG::'System Metadata'``, together with the graph
portion of ``VellisRequirements::canonicalSemanticEquality``.

The model gives associated data and links object references to their endpoints. A
graph object's identity is its UUID and the model already requires every endpoint and
direct association to resolve inside the same graph, so this realization carries
endpoint UUIDs. One object then has exactly one representation in the graph, and a
dangling reference becomes a validation finding rather than an unrepresentable object.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from vellis.json_value import JsonValue, json_equal, json_kind, normalize

__all__ = [
    "Anchor",
    "AssociatedDataObject",
    "Graph",
    "GraphObject",
    "Link",
    "LinkEndpoint",
    "MetadataError",
    "ObjectKind",
    "SystemMetadata",
    "graph_equal",
]


class ObjectKind(Enum):
    """The graph-object kinds a type key may never change."""

    ANCHOR = "anchor"
    ASSOCIATED_DATA = "associatedData"
    LINK = "link"


class MetadataError(ValueError):
    """Raised when system metadata cannot carry a Boolean live value."""


@dataclass(frozen=True, slots=True)
class SystemMetadata:
    """Canonical metadata carrying a Boolean ``live`` value.

    A missing source value normalizes to true; other JSON members are preserved.
    """

    members: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        members = {name: normalize(value) for name, value in self.members.items()}
        live = members.get("live", True)
        if not isinstance(live, bool):
            raise MetadataError(
                f"system metadata live must be a Boolean value, not {json_kind(live).value}"
            )
        members["live"] = live
        object.__setattr__(self, "members", members)

    @property
    def live(self) -> bool:
        live = self.members["live"]
        assert isinstance(live, bool)
        return live


@dataclass(frozen=True, slots=True)
class Anchor:
    """A stable, independently identifiable concept."""

    uuid: str
    type_key: str
    display_name: str
    system_metadata: SystemMetadata = field(default_factory=SystemMetadata)


@dataclass(frozen=True, slots=True)
class AssociatedDataObject:
    """An identity-bearing typed fact group grounded by one or more anchors."""

    uuid: str
    type_key: str
    anchor_uuids: tuple[str, ...] = ()
    properties: dict[str, JsonValue] = field(default_factory=dict)
    system_metadata: SystemMetadata = field(default_factory=SystemMetadata)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "properties",
            {name: normalize(value) for name, value in self.properties.items()},
        )


@dataclass(frozen=True, slots=True)
class Link:
    """An identity-bearing typed directed relationship between two endpoints."""

    uuid: str
    type_key: str
    source_uuid: str
    target_uuid: str
    system_metadata: SystemMetadata = field(default_factory=SystemMetadata)


LinkEndpoint = Anchor | AssociatedDataObject
GraphObject = Anchor | AssociatedDataObject | Link


@dataclass(frozen=True, slots=True)
class Graph:
    """Canonical graph state.

    Owned collections and direct-association sets are unordered; reordering them does
    not change graph meaning.
    """

    anchors: tuple[Anchor, ...] = ()
    associated_data: tuple[AssociatedDataObject, ...] = ()
    links: tuple[Link, ...] = ()

    def objects(self) -> tuple[GraphObject, ...]:
        return (*self.anchors, *self.associated_data, *self.links)

    def anchor(self, uuid: str) -> Anchor | None:
        return next((each for each in self.anchors if each.uuid == uuid), None)

    def associated_data_object(self, uuid: str) -> AssociatedDataObject | None:
        return next((each for each in self.associated_data if each.uuid == uuid), None)

    def link(self, uuid: str) -> Link | None:
        return next((each for each in self.links if each.uuid == uuid), None)

    def endpoint(self, uuid: str) -> LinkEndpoint | None:
        return self.anchor(uuid) or self.associated_data_object(uuid)

    @property
    def is_empty(self) -> bool:
        return not (self.anchors or self.associated_data or self.links)


def _metadata_equal(left: SystemMetadata, right: SystemMetadata) -> bool:
    return json_equal(dict(left.members), dict(right.members))


def _properties_equal(left: dict[str, JsonValue], right: dict[str, JsonValue]) -> bool:
    return json_equal(dict(left), dict(right))


def _anchors_equal(left: Graph, right: Graph) -> bool:
    first = {each.uuid: each for each in left.anchors}
    second = {each.uuid: each for each in right.anchors}
    if (
        len(first) != len(left.anchors)
        or len(second) != len(right.anchors)
        or first.keys() != second.keys()
    ):
        return False
    for uuid, anchor in first.items():
        other = second[uuid]
        if anchor.type_key != other.type_key or anchor.display_name != other.display_name:
            return False
        if not _metadata_equal(anchor.system_metadata, other.system_metadata):
            return False
    return True


def _associated_data_equal(left: Graph, right: Graph) -> bool:
    first = {each.uuid: each for each in left.associated_data}
    second = {each.uuid: each for each in right.associated_data}
    if (
        len(first) != len(left.associated_data)
        or len(second) != len(right.associated_data)
        or first.keys() != second.keys()
    ):
        return False
    for uuid, data in first.items():
        other = second[uuid]
        if data.type_key != other.type_key:
            return False
        if Counter(data.anchor_uuids) != Counter(other.anchor_uuids):
            return False
        if not _properties_equal(data.properties, other.properties):
            return False
        if not _metadata_equal(data.system_metadata, other.system_metadata):
            return False
    return True


def _links_equal(left: Graph, right: Graph) -> bool:
    first = {each.uuid: each for each in left.links}
    second = {each.uuid: each for each in right.links}
    if (
        len(first) != len(left.links)
        or len(second) != len(right.links)
        or first.keys() != second.keys()
    ):
        return False
    for uuid, link in first.items():
        other = second[uuid]
        if link.type_key != other.type_key:
            return False
        if link.source_uuid != other.source_uuid or link.target_uuid != other.target_uuid:
            return False
        if not _metadata_equal(link.system_metadata, other.system_metadata):
            return False
    return True


def graph_equal(left: Graph, right: Graph) -> bool:
    """Compare two graphs by canonical semantic equality.

    Equality includes every canonical object value, direct association, and directed
    link endpoint, and ignores order in unordered collections.
    """
    return (
        _anchors_equal(left, right)
        and _associated_data_equal(left, right)
        and _links_equal(left, right)
    )
