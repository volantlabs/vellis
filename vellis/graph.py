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
from collections.abc import Callable
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


def _grouped_equal[T: GraphObject](
    left: tuple[T, ...], right: tuple[T, ...], content_equal: Callable[[T, T], bool]
) -> bool:
    """Compare two owned collections by identity, multiplicity, and content.

    Duplicate identities are invalid, but a graph is not revalidated on every read, and
    equality still has to be reflexive on one — so duplicates are counted rather than
    collapsed or rejected outright.
    """
    first: dict[str, list[T]] = {}
    second: dict[str, list[T]] = {}
    for item in left:
        first.setdefault(item.uuid, []).append(item)
    for item in right:
        second.setdefault(item.uuid, []).append(item)
    if first.keys() != second.keys():
        return False
    for uuid, items in first.items():
        remaining = list(second[uuid])
        if len(items) != len(remaining):
            return False
        for item in items:
            for index, other in enumerate(remaining):
                if content_equal(item, other):
                    del remaining[index]
                    break
            else:
                return False
    return True


def _anchor_content_equal(one: Anchor, other: Anchor) -> bool:
    return (
        one.type_key == other.type_key
        and one.display_name == other.display_name
        and _metadata_equal(one.system_metadata, other.system_metadata)
    )


def _data_content_equal(one: AssociatedDataObject, other: AssociatedDataObject) -> bool:
    return (
        one.type_key == other.type_key
        and Counter(one.anchor_uuids) == Counter(other.anchor_uuids)
        and _properties_equal(one.properties, other.properties)
        and _metadata_equal(one.system_metadata, other.system_metadata)
    )


def _link_content_equal(one: Link, other: Link) -> bool:
    return (
        one.type_key == other.type_key
        and one.source_uuid == other.source_uuid
        and one.target_uuid == other.target_uuid
        and _metadata_equal(one.system_metadata, other.system_metadata)
    )


def graph_equal(left: Graph, right: Graph) -> bool:
    """Compare two graphs by canonical semantic equality.

    Equality includes every canonical object value, direct association, and directed
    link endpoint, and ignores order in unordered collections.
    """
    return (
        _grouped_equal(left.anchors, right.anchors, _anchor_content_equal)
        and _grouped_equal(left.associated_data, right.associated_data, _data_content_equal)
        and _grouped_equal(left.links, right.links, _link_content_equal)
    )
