from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from apps.rtg_knowledge_graph.runtime_services import VellisRuntime, VellisRuntimeServices
from components.runtime.message_runtime import (
    RuntimeAddress,
    RuntimeCausalTrace,
    RuntimeHealth,
    RuntimeHistoryPage,
    RuntimeHistoryQuery,
    RuntimeMessageEnvelope,
    RuntimeMessageOutcome,
    RuntimeReconstructionReport,
    RuntimeReconstructionRequest,
    RuntimeTraceSummaryPage,
)


class _RuntimeStub:
    def __init__(self) -> None:
        self.runtime_id = uuid4()
        self.runtime_key = "test.runtime"
        self.health = RuntimeHealth.READY
        self.position = 7
        self.reconstruction_requests: list[RuntimeReconstructionRequest] = []
        self.history_queries: list[RuntimeHistoryQuery] = []

    async def current_position(self) -> int:
        return self.position

    async def query_history(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage:
        self.history_queries.append(query)
        return RuntimeHistoryPage(())

    async def count_history(self, query: RuntimeHistoryQuery) -> int:
        self.history_queries.append(query)
        return 0

    async def query_trace_summaries(
        self,
        *,
        after_position: int | None = None,
        limit: int = 100,
        newest_first: bool = False,
        root_action_ids: tuple[str, ...] = (),
    ) -> RuntimeTraceSummaryPage:
        del after_position, limit, newest_first, root_action_ids
        return RuntimeTraceSummaryPage(())

    async def get_trace(self, trace_id: UUID) -> RuntimeCausalTrace:
        return RuntimeCausalTrace(trace_id=trace_id, facts=(), disposition=None)

    async def get_envelope(self, message_id: UUID) -> RuntimeMessageEnvelope | None:
        del message_id
        return None

    async def lookup_message_outcome(
        self, message_id: UUID
    ) -> RuntimeMessageOutcome | None:
        del message_id
        return None

    def address_for(self, instance_key: str) -> RuntimeAddress:
        del instance_key
        return RuntimeAddress(runtime_id=self.runtime_id, instance_id=uuid4())

    async def reconstruct(
        self,
        request: RuntimeReconstructionRequest,
    ) -> RuntimeReconstructionReport:
        self.reconstruction_requests.append(request)
        return RuntimeReconstructionReport(
            start_position=0,
            through_position=request.through_position or self.position,
            applied_effects=1,
            skipped_effects=0,
            incompatible_effects=0,
            verified=True,
        )


def test_runtime_services_depend_only_on_the_minimal_runtime_protocol() -> None:
    async def exercise() -> None:
        stub = _RuntimeStub()
        runtime: VellisRuntime = stub
        services = VellisRuntimeServices(runtime)

        assert await services.status() == {
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
        result = await services.reconstruct(request)
        assert result["verified"] is True
        assert result["through_position"] == 5
        assert stub.reconstruction_requests == [request]

        assert await services.migration_history() == {
            "events": [],
            "next_runtime_position": None,
            "source": "runtime_ledger",
            "through_runtime_position": 7,
        }

    asyncio.run(exercise())
