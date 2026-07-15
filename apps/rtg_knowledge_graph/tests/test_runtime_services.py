from __future__ import annotations

from uuid import UUID, uuid4

from apps.rtg_knowledge_graph.runtime_services import VellisRuntime, VellisRuntimeServices
from components.runtime.message_runtime import (
    RuntimeCausalTrace,
    RuntimeHistoryPage,
    RuntimeHistoryQuery,
    RuntimeReconstructionReport,
    RuntimeReconstructionRequest,
)


class _RuntimeStub:
    def __init__(self) -> None:
        self.runtime_id = uuid4()
        self.runtime_key = "test.runtime"
        self.health = "ready"
        self.current_position = 7
        self.reconstruction_requests: list[RuntimeReconstructionRequest] = []

    def query_history_sync(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage:
        del query
        return RuntimeHistoryPage(())

    def get_trace_sync(self, trace_id: UUID) -> RuntimeCausalTrace:
        return RuntimeCausalTrace(trace_id=trace_id, facts=(), disposition=None)

    def reconstruct_sync(
        self,
        request: RuntimeReconstructionRequest,
    ) -> RuntimeReconstructionReport:
        self.reconstruction_requests.append(request)
        return RuntimeReconstructionReport(
            start_position=0,
            through_position=request.through_position or self.current_position,
            applied_effects=1,
            skipped_effects=0,
            incompatible_effects=0,
            verified=True,
        )


def test_runtime_services_depend_only_on_the_minimal_runtime_protocol() -> None:
    stub = _RuntimeStub()
    runtime: VellisRuntime = stub
    services = VellisRuntimeServices(runtime)

    assert services.status() == {
        "runtime_id": str(stub.runtime_id),
        "runtime_key": "test.runtime",
        "health": "ready",
        "current_position": 7,
        "message_count": 0,
        "last_trace_id": None,
        "last_trace_position": None,
        "last_trace_disposition": None,
    }

    request = RuntimeReconstructionRequest(through_position=5)
    result = services.reconstruct(request)
    assert result["verified"] is True
    assert result["through_position"] == 5
    assert stub.reconstruction_requests == [request]
