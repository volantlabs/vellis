from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type RtgRoutePackRecord = JsonObject
type RtgRoutePackGateRecord = JsonObject


@dataclass(frozen=True, slots=True)
class RtgRoutePackAssemblyRequest:
    intent: JsonObject
    selected_skill: JsonObject
    scoped_tools: JsonObject
    required_docs: tuple[str, ...]
    verification_commands: tuple[JsonObject, ...]
    freshness_and_evidence: JsonObject
    identity_and_citation_rules: JsonObject
    single_graph_route: JsonObject
    federated_plan: JsonObject
    graph_contexts: tuple[JsonObject, ...]
    hazards: tuple[JsonObject, ...] = field(default_factory=tuple)


class RtgRoutePackInvalid(Exception):
    """A route-pack input or record is malformed."""


class RtgRoutePackBuilder(Protocol):
    def assemble(self, request: RtgRoutePackAssemblyRequest) -> RtgRoutePackRecord:
        """Build one advisory route-pack record from caller-supplied route evidence."""
        ...


class RtgRoutePackGate(Protocol):
    def evaluate(self, route_pack: RtgRoutePackRecord) -> RtgRoutePackGateRecord:
        """Classify a route pack into invoke, clarify, or blocked."""
        ...
