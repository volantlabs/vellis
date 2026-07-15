from __future__ import annotations

from typing import cast

from components.rtg.graph.implementation import InMemoryRtgGraph
from components.rtg.graph.protocol import RtgGraphReadView, RtgGraphSnapshot
from components.rtg.query.protocol import (
    RtgQueryEngine,
    RtgQueryError,
    RtgQueryOptions,
    RtgQueryResult,
    RtgQuerySpec,
    RtgQuerySpecInvalid,
    RtgQueryUnsupported,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ExplicitComponentAdapter,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeArgumentDescriptor,
    RuntimeClient,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.component_adapter.typed_binding import decode_typed
from components.runtime.message_runtime import (
    JsonObject,
    MessageRuntime,
    RuntimeAddress,
    RuntimeMessageKind,
    RuntimeReplayMode,
)

_CONTRACT = "component.rtg.query"
_ACTION = f"{_CONTRACT}.execute"
_REQUEST_CODEC = f"codec.python.{_CONTRACT}.request.json"


class _BoundQueryService:
    def __init__(self, engine: RtgQueryEngine) -> None:
        self._engine = engine

    def execute(
        self,
        graph_snapshot: RtgGraphSnapshot,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        return self._engine.execute(
            InMemoryRtgGraph.import_snapshot(graph_snapshot), query_spec, query_options
        )


def create_rtg_query_adapter(query: RtgQueryEngine) -> ExplicitComponentAdapter:
    service = _BoundQueryService(query)
    return ExplicitComponentAdapter(
        (
            ActionBinding(
                descriptor=RuntimeActionBindingDescriptor(
                    component_contract_id=_CONTRACT,
                    action_id=_ACTION,
                    binding_id="binding.python.rtg.query.v1",
                    binding_version=1,
                    schema_version=1,
                    request_codec_id=_REQUEST_CODEC,
                    result_codec_id=f"codec.python.{_CONTRACT}.result.json",
                    failure_codec_id=f"codec.python.{_CONTRACT}.failure.json",
                    idempotency=RuntimeActionIdempotency.IDEMPOTENT,
                    replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
                    request_arguments=(
                        RuntimeArgumentDescriptor("graph_snapshot", required=True),
                        RuntimeArgumentDescriptor("query_spec", required=True),
                        RuntimeArgumentDescriptor("query_options", required=False, default=None),
                    ),
                ),
                invoke=service.execute,
                decode_request=lambda payload: (
                    (),
                    {
                        "graph_snapshot": decode_typed(payload["graph_snapshot"], RtgGraphSnapshot),
                        "query_spec": decode_typed(payload["query_spec"], RtgQuerySpec),
                        "query_options": decode_typed(
                            payload.get("query_options"), RtgQueryOptions | None
                        ),
                    },
                ),
                encode_result=encode_json,
                failure_types=(RtgQuerySpecInvalid, RtgQueryUnsupported),
            ),
        )
    )


class RtgQueryMessageProxy:
    def __init__(
        self, runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
    ) -> None:
        self._client = RuntimeClient(
            runtime,
            source=source,
            target=target,
            component_contract_id=_CONTRACT,
            request_codec_id=_REQUEST_CODEC,
        )

    def execute(
        self,
        graph: RtgGraphReadView,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        export_snapshot = getattr(graph, "export_snapshot", None)
        if not callable(export_snapshot):
            raise RtgQueryError("runtime query binding requires a snapshot-capable graph read view")
        arguments: JsonObject = {
            "graph_snapshot": encode_json(export_snapshot()),
            "query_spec": encode_json(query_spec),
            "query_options": encode_json(query_options),
        }
        outcome = self._client.request_sync(_ACTION, arguments)
        payload = outcome.response.payload.value
        if not isinstance(payload, dict):
            raise RtgQueryError("query response payload is not an object")
        if outcome.response.kind is RuntimeMessageKind.FAULT:
            error_type = str(payload.get("type", "RtgQueryError"))
            error_class = {
                "RtgQuerySpecInvalid": RtgQuerySpecInvalid,
                "RtgQueryUnsupported": RtgQueryUnsupported,
            }.get(error_type, RtgQueryError)
            evidence = payload.get("evidence")
            diagnostic = evidence.get("diagnostic") if isinstance(evidence, dict) else None
            raise error_class(
                str(payload.get("message", error_type)),
                diagnostic=cast(JsonObject, diagnostic) if isinstance(diagnostic, dict) else None,
            )
        return cast(RtgQueryResult, decode_typed(payload.get("result"), RtgQueryResult))


def create_rtg_query_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> RtgQueryEngine:
    return RtgQueryMessageProxy(runtime, source, target)
