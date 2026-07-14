from __future__ import annotations

import copy
import re
from uuid import UUID

from components.rtg.bridge_traversal.protocol import (
    RtgBridgeEndpointResolver,
    RtgBridgeTraversalEndpoint,
    RtgBridgeTraversalInvalid,
    RtgBridgeTraversalNotAllowed,
    RtgBridgeTraversalRecord,
    RtgBridgeTraversalRequest,
)
from components.rtg.citation_resolution import (
    RtgCitationResolutionRecord,
    RtgCitationResolutionRequest,
)
from components.rtg.graph_bridge import (
    RtgGraphBridge,
    RtgGraphLocalReference,
)

_IDENTIFIER_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")


class DeterministicRtgBridgeTraverser:
    """Read-only single-bridge traversal implementation."""

    def __init__(
        self,
        bridge_store: RtgGraphBridge,
        citation_resolver: RtgBridgeEndpointResolver,
    ) -> None:
        self._bridge_store = bridge_store
        self._citation_resolver = citation_resolver

    @classmethod
    def open(
        cls,
        bridge_store: RtgGraphBridge,
        citation_resolver: RtgBridgeEndpointResolver,
    ) -> DeterministicRtgBridgeTraverser:
        return cls(bridge_store, citation_resolver)

    def traverse(self, request: RtgBridgeTraversalRequest) -> RtgBridgeTraversalRecord:
        bridge_id = _validate_identifier(request.bridge_id, "request.bridge_id")
        bridge = self._bridge_store.get_bridge(bridge_id)
        if bridge.status != "active":
            raise RtgBridgeTraversalNotAllowed(
                f"bridge {bridge.bridge_id} is {bridge.status}, not active"
            )

        source_resolution = self._resolve_endpoint(bridge.source)
        target_resolution = self._resolve_endpoint(bridge.target)
        status = _traversal_status(source_resolution, target_resolution)
        return RtgBridgeTraversalRecord(
            status=status,
            bridge=copy.deepcopy(bridge),
            source=RtgBridgeTraversalEndpoint(
                reference=copy.deepcopy(bridge.source),
                resolution=copy.deepcopy(source_resolution),
            ),
            target=RtgBridgeTraversalEndpoint(
                reference=copy.deepcopy(bridge.target),
                resolution=copy.deepcopy(target_resolution),
            ),
        )

    def _resolve_endpoint(
        self,
        reference: RtgGraphLocalReference,
    ) -> RtgCitationResolutionRecord:
        resolution = self._citation_resolver.resolve(
            RtgCitationResolutionRequest(
                graph_id=reference.graph_id,
                local_uuid=str(reference.local_uuid),
            )
        )
        _validate_resolution_identity(reference, resolution)
        return resolution


def _traversal_status(
    source: RtgCitationResolutionRecord,
    target: RtgCitationResolutionRecord,
) -> str:
    resolved_count = sum(
        1 for resolution in (source, target) if resolution.status == "resolved"
    )
    if resolved_count == 2:
        return "resolved"
    if resolved_count == 1:
        return "partial"
    return "unresolved"


def _validate_resolution_identity(
    reference: RtgGraphLocalReference,
    resolution: RtgCitationResolutionRecord,
) -> None:
    try:
        resolution_uuid = UUID(resolution.local_uuid)
    except ValueError as error:
        raise RtgBridgeTraversalInvalid(
            "endpoint resolution local_uuid must be a UUID"
        ) from error
    if resolution.graph_id != reference.graph_id or resolution_uuid != reference.local_uuid:
        raise RtgBridgeTraversalInvalid(
            "endpoint resolution identity must match the bridge endpoint"
        )
    if resolution.status not in {"resolved", "not_found", "unsupported"}:
        raise RtgBridgeTraversalInvalid(
            "endpoint resolution status must be resolved, not_found, or unsupported"
        )


def _validate_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgBridgeTraversalInvalid(f"{name} must be a non-empty string")
    text = value.strip()
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise RtgBridgeTraversalInvalid(f"{name} must be an identifier")
    return text
