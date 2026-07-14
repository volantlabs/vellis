from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RtgCitationResolutionRequest:
    graph_id: str
    local_uuid: str


@dataclass(frozen=True, slots=True)
class RtgCitationProjectionSpec:
    graph_id: str
    query_name: str
    anchor_bucket: str


@dataclass(frozen=True, slots=True)
class RtgCitationProjectionRead:
    projection: RtgCitationProjectionSpec
    rows: tuple[JsonObject, ...]
    provenance: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgCitationResolutionRecord:
    status: str
    graph_id: str
    local_uuid: str
    query_name: str | None = None
    anchor_bucket: str | None = None
    records: tuple[JsonObject, ...] = ()
    provenance: JsonObject = field(default_factory=dict)


class RtgCitationResolutionError(Exception):
    """Base class for citation resolution errors."""


class RtgCitationResolutionInvalid(RtgCitationResolutionError):
    """A request or dependency result violates the resolution contract."""


class RtgCitationProjectionCatalog(Protocol):
    def get_projection(self, graph_id: str) -> RtgCitationProjectionSpec | None:
        """Return the one citation projection declared for a graph, if any."""
        ...


class RtgCitationProjectionReader(Protocol):
    def read_projection(
        self,
        projection: RtgCitationProjectionSpec,
    ) -> RtgCitationProjectionRead:
        """Execute one bounded citation projection without mutation."""
        ...


class RtgCitationResolver(Protocol):
    @classmethod
    def open(
        cls,
        catalog: RtgCitationProjectionCatalog,
        reader: RtgCitationProjectionReader,
    ) -> RtgCitationResolver:
        """Open a resolver over projection catalog and reader dependencies."""
        ...

    def resolve(self, request: RtgCitationResolutionRequest) -> RtgCitationResolutionRecord:
        """Resolve one graph-qualified citation through its declared projection."""
        ...
