from __future__ import annotations

import copy
from uuid import UUID

import pytest

from components.rtg.bridge_traversal import (
    DeterministicRtgBridgeTraverser,
    RtgBridgeTraversalInvalid,
    RtgBridgeTraversalNotAllowed,
    RtgBridgeTraversalRequest,
)
from components.rtg.citation_resolution import (
    RtgCitationResolutionRecord,
    RtgCitationResolutionRequest,
)
from components.rtg.graph_bridge import (
    InMemoryRtgGraphBridge,
    RtgGraphBridgeAssertion,
    RtgGraphBridgeDraft,
    RtgGraphBridgeInvalid,
    RtgGraphLocalReference,
)

MODEL_EVIDENCE = {
    "TraverseBridgeContractVerification": (
        "test_traverse_resolves_one_active_bridge_without_mutation",
        "test_traverse_reports_partial_and_unresolved_endpoint_results",
        "test_traverse_rejects_revoked_bridge_before_resolution",
        "test_traverse_does_not_accept_candidate_or_malformed_identifier",
        "test_traverse_rejects_mismatched_endpoint_resolution_identity",
        "test_traverse_rejects_invalid_source_status_before_target_resolution",
    ),
    "OpenRtgBridgeTraverserContractVerification": (
        "test_open_retains_dependencies_without_reading",
    ),
    "RtgBridgeTraverserBoundaryVerification": (
        "test_open_retains_dependencies_without_reading",
        "test_traverse_resolves_one_active_bridge_without_mutation",
        "test_traverse_reports_partial_and_unresolved_endpoint_results",
        "test_traverse_rejects_revoked_bridge_before_resolution",
        "test_traverse_does_not_accept_candidate_or_malformed_identifier",
        "test_traverse_rejects_mismatched_endpoint_resolution_identity",
        "test_traverser_surface_does_not_expose_adjacent_operations",
    ),
}

SOURCE = RtgGraphLocalReference(
    graph_id="repo_twin",
    local_uuid=UUID("11111111-1111-4111-8111-111111111111"),
)
TARGET = RtgGraphLocalReference(
    graph_id="personal_ops",
    local_uuid=UUID("22222222-2222-4222-8222-222222222222"),
)


class FakeCitationResolver:
    def __init__(self, statuses: dict[str, str] | None = None) -> None:
        self.statuses = statuses or {}
        self.calls: list[RtgCitationResolutionRequest] = []

    def resolve(self, request: RtgCitationResolutionRequest) -> RtgCitationResolutionRecord:
        self.calls.append(request)
        status = self.statuses.get(request.graph_id, "resolved")
        return RtgCitationResolutionRecord(
            status=status,
            graph_id=request.graph_id,
            local_uuid=request.local_uuid,
            query_name="bounded_projection" if status != "unsupported" else None,
            anchor_bucket="item" if status != "unsupported" else None,
            records=(
                {
                    "anchors": {"item": request.local_uuid},
                    "properties": {"facts": {"graph": request.graph_id}},
                },
            )
            if status == "resolved"
            else (),
        )


class RecordingBridgeStore(InMemoryRtgGraphBridge):
    def __init__(self) -> None:
        super().__init__()
        self.get_calls: list[str] = []

    def get_bridge(self, bridge_id: str) -> RtgGraphBridgeAssertion:
        self.get_calls.append(bridge_id)
        return super().get_bridge(bridge_id)


def bridge_store(
    store: InMemoryRtgGraphBridge | None = None,
) -> tuple[InMemoryRtgGraphBridge, str]:
    store = store or InMemoryRtgGraphBridge.empty()
    bridge = store.put_bridge(
        RtgGraphBridgeDraft(
            bridge_type="related_context",
            source=SOURCE,
            target=TARGET,
            confidence=0.75,
            asserted_at="2026-07-10T00:00:00Z",
            asserted_by="agent.codex",
            provenance=(SOURCE,),
            metadata={"reason": "test"},
        )
    )
    return store, bridge.bridge_id


def test_open_retains_dependencies_without_reading() -> None:
    store, _ = bridge_store(RecordingBridgeStore())
    resolver = FakeCitationResolver()

    traverser = DeterministicRtgBridgeTraverser.open(store, resolver)

    assert traverser is not None
    assert isinstance(store, RecordingBridgeStore)
    assert store.get_calls == []
    assert resolver.calls == []


def test_traverse_resolves_one_active_bridge_without_mutation() -> None:
    store, bridge_id = bridge_store(RecordingBridgeStore())
    resolver = FakeCitationResolver()
    traverser = DeterministicRtgBridgeTraverser.open(store, resolver)
    before = copy.deepcopy(store.get_bridge(bridge_id))
    assert isinstance(store, RecordingBridgeStore)
    store.get_calls.clear()

    result = traverser.traverse(RtgBridgeTraversalRequest(bridge_id=bridge_id))

    assert result.status == "resolved"
    assert result.bridge == before
    assert result.bridge is not before
    assert result.source.reference == SOURCE
    assert result.target.reference == TARGET
    assert result.source.resolution.status == "resolved"
    assert result.target.resolution.status == "resolved"
    assert resolver.calls == [
        RtgCitationResolutionRequest(
            graph_id=SOURCE.graph_id,
            local_uuid=str(SOURCE.local_uuid),
        ),
        RtgCitationResolutionRequest(
            graph_id=TARGET.graph_id,
            local_uuid=str(TARGET.local_uuid),
        ),
    ]
    assert store.get_calls == [bridge_id]
    assert store.get_bridge(bridge_id) == before


@pytest.mark.parametrize(
    ("statuses", "expected"),
    (
        ({"personal_ops": "not_found"}, "partial"),
        ({"repo_twin": "unsupported", "personal_ops": "not_found"}, "unresolved"),
    ),
)
def test_traverse_reports_partial_and_unresolved_endpoint_results(
    statuses: dict[str, str],
    expected: str,
) -> None:
    store, bridge_id = bridge_store()
    traverser = DeterministicRtgBridgeTraverser.open(
        store,
        FakeCitationResolver(statuses),
    )

    result = traverser.traverse(RtgBridgeTraversalRequest(bridge_id=bridge_id))

    assert result.status == expected
    assert result.source.resolution.status == statuses.get("repo_twin", "resolved")
    assert result.target.resolution.status == statuses.get("personal_ops", "resolved")


def test_traverse_rejects_revoked_bridge_before_resolution() -> None:
    store, bridge_id = bridge_store()
    store.revoke_bridge(
        bridge_id,
        revoked_at="2026-07-10T01:00:00Z",
        revoked_by="agent.codex",
        reason="expired",
    )
    resolver = FakeCitationResolver()
    traverser = DeterministicRtgBridgeTraverser.open(store, resolver)

    with pytest.raises(RtgBridgeTraversalNotAllowed, match="not active"):
        traverser.traverse(RtgBridgeTraversalRequest(bridge_id=bridge_id))

    assert resolver.calls == []


def test_traverse_does_not_accept_candidate_or_malformed_identifier() -> None:
    store, _ = bridge_store()
    resolver = FakeCitationResolver()
    traverser = DeterministicRtgBridgeTraverser.open(store, resolver)

    with pytest.raises(RtgGraphBridgeInvalid):
        traverser.traverse(RtgBridgeTraversalRequest(bridge_id="candidate_deadbeef"))
    with pytest.raises(RtgBridgeTraversalInvalid):
        traverser.traverse(RtgBridgeTraversalRequest(bridge_id="bridge-id"))

    assert resolver.calls == []


def test_traverse_rejects_mismatched_endpoint_resolution_identity() -> None:
    store, bridge_id = bridge_store()

    class MismatchedResolver:
        def resolve(
            self,
            request: RtgCitationResolutionRequest,
        ) -> RtgCitationResolutionRecord:
            return RtgCitationResolutionRecord(
                status="resolved",
                graph_id="wrong_graph",
                local_uuid=request.local_uuid,
            )

    traverser = DeterministicRtgBridgeTraverser.open(store, MismatchedResolver())

    with pytest.raises(RtgBridgeTraversalInvalid, match="must match"):
        traverser.traverse(RtgBridgeTraversalRequest(bridge_id=bridge_id))


def test_traverse_rejects_invalid_source_status_before_target_resolution() -> None:
    store, bridge_id = bridge_store()
    resolver = FakeCitationResolver({"repo_twin": "unexpected"})
    traverser = DeterministicRtgBridgeTraverser.open(store, resolver)

    with pytest.raises(RtgBridgeTraversalInvalid, match="resolution status"):
        traverser.traverse(RtgBridgeTraversalRequest(bridge_id=bridge_id))

    assert resolver.calls == [
        RtgCitationResolutionRequest(
            graph_id=SOURCE.graph_id,
            local_uuid=str(SOURCE.local_uuid),
        )
    ]


def test_traverser_surface_does_not_expose_adjacent_operations() -> None:
    store, _ = bridge_store()
    traverser = DeterministicRtgBridgeTraverser.open(store, FakeCitationResolver())

    assert not hasattr(traverser, "find_bridges")
    assert not hasattr(traverser, "promote_candidate")
    assert not hasattr(traverser, "resolve")
    assert not hasattr(traverser, "query")
