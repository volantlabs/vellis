from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import uuid5

from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ComponentEndpoint,
    ComponentExecution,
)
from components.runtime.message_runtime import SqliteMessageRuntime
from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    JsonObject,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeDeliveryStatus,
    RuntimeHistoryQuery,
    RuntimeLaneDeclaration,
    RuntimeMessageConflict,
    RuntimeReplayMode,
    RuntimeTopologyManifest,
    topology_manifest_hash,
)

_CONTRACT = "component.test.ordinary"
_BINDING = "binding.test.ordinary"


class _Counter:
    def __init__(self) -> None:
        self.value = 0

    def add(self, amount: int) -> int:
        self.value += amount
        return self.value


def _descriptor(action_id: str, *, lane: str = "serialized") -> RuntimeActionBindingDescriptor:
    return RuntimeActionBindingDescriptor(
        component_contract_id=_CONTRACT,
        action_id=action_id,
        binding_id=_BINDING,
        binding_version=1,
        schema_version=1,
        request_codec_id=f"{_BINDING}.{action_id}.request.json",
        result_codec_id=f"{_BINDING}.{action_id}.result.json",
        failure_codec_id=f"{_BINDING}.{action_id}.failure.json",
        idempotency=RuntimeActionIdempotency.UNSPECIFIED,
        replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
        concurrency_lane=lane,
    )


def _decode_amount(payload: JsonObject) -> tuple[tuple[object, ...], dict[str, object]]:
    return (int(payload["amount"]),), {}


def _adapter(counter: _Counter, peer_key: str) -> ComponentAdapter:
    add = ActionBinding(
        descriptor=_descriptor("add", lane="local"),
        decode_request=_decode_amount,
        encode_result=lambda result: int(cast(int, result)),
        invoke=counter.add,
    )

    async def coordinate(
        args: tuple[object, ...],
        _kwargs: dict[str, object],
        execution: ComponentExecution,
    ) -> None:
        result = await execution.call(
            "peer-add",
            add.descriptor.action_ref(),
            {"amount": int(cast(int, args[0]))},
            target=execution.address_for(peer_key),
        )
        repeated = await execution.call(
            "peer-add",
            add.descriptor.action_ref(),
            {"amount": int(cast(int, args[0]))},
            target=execution.address_for(peer_key),
        )
        try:
            await execution.call(
                "peer-add",
                add.descriptor.action_ref(),
                {"amount": int(cast(int, args[0])) + 1},
                target=execution.address_for(peer_key),
            )
        except RuntimeMessageConflict:
            conflict_rejected = True
        else:
            conflict_rejected = False
        await execution.complete(
            {
                "peer_value": result,
                "repeated_value": repeated,
                "conflict_rejected": conflict_rejected,
            }
        )

    return ComponentAdapter(
        (
            add,
            ActionBinding(
                descriptor=_descriptor("coordinate", lane="coordination"),
                decode_request=_decode_amount,
                encode_result=lambda result: result,
                handler=coordinate,
            ),
        )
    )


def test_one_adapter_hosts_local_and_coordinating_actions_across_same_type_occurrences(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime = SqliteMessageRuntime(tmp_path / "runtime.sqlite", runtime_key="test.vertical")
        left = _adapter(_Counter(), "worker.right")
        right_counter = _Counter()
        right = _adapter(right_counter, "worker.left")
        ingress = ComponentAdapter(
            binding_id="binding.test.ingress",
            component_contract_id="component.test.ingress",
        )
        occurrences = (
            ComponentOccurrenceDeclaration(
                "worker.left",
                _CONTRACT,
                _BINDING,
                1,
                lanes=(
                    RuntimeLaneDeclaration("local", worker_limit=2),
                    RuntimeLaneDeclaration("coordination"),
                ),
            ),
            ComponentOccurrenceDeclaration(
                "worker.right",
                _CONTRACT,
                _BINDING,
                1,
                lanes=(
                    RuntimeLaneDeclaration("local", worker_limit=2),
                    RuntimeLaneDeclaration("coordination"),
                ),
            ),
            ComponentOccurrenceDeclaration(
                "ingress",
                "component.test.ingress",
                "binding.test.ingress",
                1,
            ),
        )
        manifest = RuntimeTopologyManifest(
            runtime_key="test.vertical",
            manifest_schema_version=4,
            occurrences=occurrences,
            curated_operations=(),
            manifest_hash="",
        )
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        await runtime.prepare_static_topology(manifest)
        registrations = {
            declaration.instance_key: await runtime.register_occurrence(declaration)
            for declaration in occurrences
        }
        await runtime.attach_participant(
            registrations["worker.left"], left, left.describe().actions
        )
        await runtime.attach_participant(
            registrations["worker.right"], right, right.describe().actions
        )
        await runtime.attach_participant(registrations["ingress"], ingress)
        await runtime.confirm_static_topology(manifest)

        endpoint = ComponentEndpoint(
            runtime,
            ingress,
            source=runtime.address_for("ingress"),
        )
        outcome = await endpoint.request(
            _descriptor("coordinate", lane="coordination").action_ref(),
            {"amount": 3},
            target=runtime.address_for("worker.left"),
        )

        assert outcome.response.payload.value == {
            "result": {
                "peer_value": 3,
                "repeated_value": 3,
                "conflict_rejected": True,
            }
        }
        assert right_counter.value == 3
        assert outcome.terminal_position > outcome.request.accepted_position
        trace = await runtime.get_trace(outcome.request.trace_id, include_payload=True)
        assert trace.disposition is not None
        accepted = [
            fact.envelope
            for fact in trace.facts
            if fact.fact_type == "message_accepted" and fact.envelope is not None
        ]
        assert [envelope.kind.value for envelope in accepted] == [
            "request",
            "request",
            "response",
            "response",
        ]
        assert accepted[1].message_id == uuid5(outcome.request.message_id, "peer-add")
        for status in (RuntimeDeliveryStatus.ACCEPTED, RuntimeDeliveryStatus.DELIVERING):
            page = await runtime.query_history(
                RuntimeHistoryQuery(
                    trace_id=outcome.request.trace_id,
                    delivery_status=status,
                )
            )
            assert page.facts == ()
        await runtime.aclose()

    asyncio.run(exercise())
