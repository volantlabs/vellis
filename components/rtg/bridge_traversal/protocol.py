from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from components.rtg.citation_resolution import (
    RtgCitationResolutionRecord,
    RtgCitationResolutionRequest,
)
from components.rtg.graph_bridge import (
    RtgGraphBridge,
    RtgGraphBridgeAssertion,
    RtgGraphLocalReference,
)


@dataclass(frozen=True, slots=True)
class RtgBridgeTraversalRequest:
    bridge_id: str


@dataclass(frozen=True, slots=True)
class RtgBridgeTraversalEndpoint:
    reference: RtgGraphLocalReference
    resolution: RtgCitationResolutionRecord


@dataclass(frozen=True, slots=True)
class RtgBridgeTraversalRecord:
    status: str
    bridge: RtgGraphBridgeAssertion
    source: RtgBridgeTraversalEndpoint
    target: RtgBridgeTraversalEndpoint


class RtgBridgeTraversalError(Exception):
    """Base class for bridge traversal errors."""


class RtgBridgeTraversalInvalid(RtgBridgeTraversalError):
    """A request or dependency result violates the traversal contract."""


class RtgBridgeTraversalNotAllowed(RtgBridgeTraversalError):
    """A bridge assertion does not grant traversal permission."""


class RtgBridgeEndpointResolver(Protocol):
    def resolve(self, request: RtgCitationResolutionRequest) -> RtgCitationResolutionRecord:
        """Resolve one graph-qualified bridge endpoint."""
        ...


class RtgBridgeTraverser(Protocol):
    @classmethod
    def open(
        cls,
        bridge_store: RtgGraphBridge,
        citation_resolver: RtgBridgeEndpointResolver,
    ) -> RtgBridgeTraverser:
        """Open a traverser over bridge and citation-resolution dependencies."""
        ...

    def traverse(self, request: RtgBridgeTraversalRequest) -> RtgBridgeTraversalRecord:
        """Resolve both endpoints of one explicit active bridge assertion."""
        ...
