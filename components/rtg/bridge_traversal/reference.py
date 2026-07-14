from __future__ import annotations

from uuid import UUID

from components.rtg.bridge_traversal import (
    DeterministicRtgBridgeTraverser,
    RtgBridgeTraversalRequest,
)
from components.rtg.citation_resolution import (
    RtgCitationResolutionRecord,
    RtgCitationResolutionRequest,
)
from components.rtg.graph_bridge import (
    InMemoryRtgGraphBridge,
    RtgGraphBridgeDraft,
    RtgGraphLocalReference,
)


class ExampleCitationResolver:
    def resolve(self, request: RtgCitationResolutionRequest) -> RtgCitationResolutionRecord:
        return RtgCitationResolutionRecord(
            status="resolved",
            graph_id=request.graph_id,
            local_uuid=request.local_uuid,
            query_name="example_projection",
            anchor_bucket="item",
            records=(
                {
                    "anchors": {"item": request.local_uuid},
                    "properties": {"facts": {"title": request.graph_id}},
                },
            ),
        )


def create_reference_component() -> tuple[DeterministicRtgBridgeTraverser, str]:
    source = RtgGraphLocalReference(
        graph_id="source_graph",
        local_uuid=UUID("11111111-1111-4111-8111-111111111111"),
    )
    target = RtgGraphLocalReference(
        graph_id="target_graph",
        local_uuid=UUID("22222222-2222-4222-8222-222222222222"),
    )
    store = InMemoryRtgGraphBridge.empty()
    bridge = store.put_bridge(
        RtgGraphBridgeDraft(
            bridge_type="related_context",
            source=source,
            target=target,
            confidence=0.8,
            asserted_at="2026-07-10T00:00:00Z",
            asserted_by="example",
            provenance=(source,),
        )
    )
    return DeterministicRtgBridgeTraverser.open(store, ExampleCitationResolver()), bridge.bridge_id


def main() -> None:
    traverser, bridge_id = create_reference_component()
    print(traverser.traverse(RtgBridgeTraversalRequest(bridge_id=bridge_id)))


if __name__ == "__main__":
    main()
