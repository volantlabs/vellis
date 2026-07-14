from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RtgDiscoveryCell:
    row_key: str
    column_key: str
    description: str
    anchor_type_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RtgDiscoveryCoordinates:
    row_key: str
    column_key: str


@dataclass(frozen=True, slots=True)
class RtgDiscoveryView:
    view_id: str
    description: str
    row_labels: dict[str, str]
    column_labels: dict[str, str]
    cells: tuple[RtgDiscoveryCell, ...]
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgDiscoverySelection:
    view_id: str
    coordinates: tuple[RtgDiscoveryCoordinates, ...]
    anchor_type_keys: tuple[str, ...]
    cell_descriptions: dict[RtgDiscoveryCoordinates, str]


@dataclass(frozen=True, slots=True)
class RtgDiscoveryViewList:
    views: tuple[RtgDiscoveryView, ...]


class RtgDiscoveryError(Exception):
    """Base class for RTG Discovery errors."""


class RtgDiscoveryViewInvalid(RtgDiscoveryError):
    """A discovery view is malformed."""


class RtgDiscoveryViewNotFound(RtgDiscoveryError):
    """A requested discovery view does not exist."""


class RtgDiscoverySelectionInvalid(RtgDiscoveryError):
    """A discovery selection is malformed or references an empty coordinate."""


class RtgDiscovery(Protocol):
    @classmethod
    def empty(cls) -> RtgDiscovery:
        """Create an empty curated discovery registry."""
        ...

    def put_view(self, view: RtgDiscoveryView) -> RtgDiscoveryView:
        """Create or fully replace one curated discovery view."""
        ...

    def list_views(self) -> RtgDiscoveryViewList:
        """List curated discovery views."""
        ...

    def select_anchor_types(
        self,
        view_id: str,
        coordinates: tuple[RtgDiscoveryCoordinates, ...],
    ) -> RtgDiscoverySelection:
        """Return anchor type keys for selected discovery-view coordinates."""
        ...
