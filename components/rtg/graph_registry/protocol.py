from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RtgGraphMcpEndpoint:
    transport: str
    host: str | None = None
    port: int | None = None
    path: str = "/mcp"
    server_name: str | None = None


@dataclass(frozen=True, slots=True)
class RtgGraphDescriptor:
    graph_id: str
    title: str
    storage_root: str
    sql_database_path: str
    authority: str
    write_policy: str
    domains: tuple[str, ...]
    tags: tuple[str, ...] = ()
    mcp_endpoint: RtgGraphMcpEndpoint | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgGraphList:
    graphs: tuple[RtgGraphDescriptor, ...]


@dataclass(frozen=True, slots=True)
class RtgGraphIntent:
    operation: str
    text: str
    target_graph_id: str | None = None
    domain_hints: tuple[str, ...] = ()
    tag_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgGraphRouteCandidate:
    graph_id: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RtgGraphRouteRecord:
    intent: RtgGraphIntent
    candidates: tuple[RtgGraphRouteCandidate, ...]
    selected_graph_id: str | None
    requires_confirmation: bool
    reason: str


@dataclass(frozen=True, slots=True)
class RtgGraphFederatedIntent:
    operation: str
    text: str
    target_graph_ids: tuple[str, ...] = ()
    domain_hints: tuple[str, ...] = ()
    tag_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgGraphFederatedPlanStep:
    graph_id: str
    operation: str
    intent_text: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RtgGraphFederatedPlan:
    intent: RtgGraphFederatedIntent
    steps: tuple[RtgGraphFederatedPlanStep, ...]
    requires_confirmation: bool
    executable: bool
    reason: str


class RtgGraphRegistryError(Exception):
    """Base class for RTG Graph Registry errors."""


class RtgGraphRegistryInvalid(RtgGraphRegistryError):
    """A graph descriptor or intent is malformed."""


class RtgGraphNotFound(RtgGraphRegistryError):
    """A requested graph descriptor does not exist."""


class RtgGraphRegistry(Protocol):
    @classmethod
    def empty(cls) -> RtgGraphRegistry:
        """Create an empty graph registry."""
        ...

    def put_graph(self, graph: RtgGraphDescriptor) -> RtgGraphDescriptor:
        """Create or fully replace one graph descriptor."""
        ...

    def list_graphs(self) -> RtgGraphList:
        """List graph descriptors."""
        ...

    def get_graph(self, graph_id: str) -> RtgGraphDescriptor:
        """Return one graph descriptor by id."""
        ...

    def compile_intent(self, intent: RtgGraphIntent) -> RtgGraphRouteRecord:
        """Compile an intent into ranked candidate graph routes."""
        ...

    def compile_federated_intent(self, intent: RtgGraphFederatedIntent) -> RtgGraphFederatedPlan:
        """Compile an intent into graph-local federated plan steps."""
        ...
