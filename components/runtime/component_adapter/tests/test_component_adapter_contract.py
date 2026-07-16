from __future__ import annotations

import asyncio
from dataclasses import fields, replace
from pathlib import Path

import pytest

from components.rtg.graph import (
    RTG_GRAPH_ACTIONS,
    InMemoryRtgGraph,
    RtgAnchor,
)
from components.rtg.graph.runtime_binding import create_rtg_graph_adapter
from components.runtime.component_adapter import (
    ActionRef,
    ComponentAdapter,
    ComponentEndpoint,
    ReplayStateBinding,
    RuntimeActionBindingDescriptor,
    RuntimeBindingInvalid,
    decode_typed,
)
from components.runtime.message_runtime import (
    RuntimeActionUnknown,
    RuntimeHistoryQuery,
    SqliteMessageRuntime,
)
from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    RuntimeRequestOutcome,
    RuntimeTopologyManifest,
    topology_manifest_hash,
)

MODEL_EVIDENCE = {
    "ComponentRuntimeAdapterBoundaryVerification": (
        "test_direct_and_message_invocation_are_equivalent_and_effect_is_canonical",
        "test_private_methods_and_role_kinds_are_absent",
    ),
    "DeliverRuntimeEnvelopeContractVerification": (
        "test_direct_and_message_invocation_are_equivalent_and_effect_is_canonical",
    ),
    "ComponentRuntimeReplayVerification": (
        "test_direct_and_message_invocation_are_equivalent_and_effect_is_canonical",
    ),
    "DescribeRuntimeBindingContractVerification": (
        "test_private_methods_and_role_kinds_are_absent",
    ),
    "ApplyCanonicalReplayEffectContractVerification": (
        "test_direct_and_message_invocation_are_equivalent_and_effect_is_canonical",
    ),
    "ReplayStateStatusContractVerification": (
        "test_replay_state_operations_are_composed_not_subclassed",
    ),
    "ResetReplayStateContractVerification": (
        "test_replay_state_operations_are_composed_not_subclassed",
    ),
    "ImportReplayCheckpointContractVerification": (
        "test_replay_state_operations_are_composed_not_subclassed",
    ),
    "ReplayStateDigestContractVerification": (
        "test_replay_state_operations_are_composed_not_subclassed",
    ),
    "VerifyReplayStateContractVerification": (
        "test_replay_state_operations_are_composed_not_subclassed",
    ),
}


async def _graph_runtime(
    path: Path, graph: InMemoryRtgGraph
) -> tuple[SqliteMessageRuntime, ComponentEndpoint, ComponentAdapter]:
    adapter = create_rtg_graph_adapter(graph)
    ingress = ComponentAdapter(
        binding_id="binding.test.ingress", component_contract_id="component.test.ingress"
    )
    declarations = (
        ComponentOccurrenceDeclaration(
            "graph", "component.rtg.graph", adapter.describe().binding_id, 1
        ),
        ComponentOccurrenceDeclaration(
            "ingress", "component.test.ingress", "binding.test.ingress", 1
        ),
    )
    manifest = RuntimeTopologyManifest("adapter.test", 4, declarations, (), "")
    manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
    runtime = SqliteMessageRuntime(path, runtime_key="adapter.test")
    await runtime.prepare_static_topology(manifest)
    for declaration, participant in zip(declarations, (adapter, ingress), strict=True):
        registration = await runtime.register_occurrence(declaration)
        await runtime.attach_participant(registration, participant, participant.describe().actions)
    await runtime.confirm_static_topology(manifest)
    return (
        runtime,
        ComponentEndpoint(runtime, ingress, source=runtime.address_for("ingress")),
        adapter,
    )


def test_direct_and_message_invocation_are_equivalent_and_effect_is_canonical(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        direct = InMemoryRtgGraph.empty()
        expected = direct.put_anchor(RtgAnchor(None, "Person"))
        mediated = InMemoryRtgGraph.empty()
        runtime, endpoint, _adapter = await _graph_runtime(tmp_path / "runtime.sqlite", mediated)
        outcome = await endpoint.request(
            RTG_GRAPH_ACTIONS["put_anchor"],
            {"anchor": RtgAnchor(expected.uuid, "Person")},
            target=runtime.address_for("graph"),
        )
        payload = outcome.response.payload.value
        assert isinstance(payload, dict)
        actual = decode_typed(payload["result"], RtgAnchor)
        assert actual == expected
        effects = (
            await runtime.query_history(
                RuntimeHistoryQuery(trace_id=outcome.request.trace_id, fact_type="canonical_effect")
            )
        ).facts
        assert len(effects) == 1
        assert "effect" not in effects[0].details
        effect_payload_hash = effects[0].details["effect_payload_hash"]
        assert isinstance(effect_payload_hash, str)
        assert len(effect_payload_hash) == 64
        await runtime.aclose()

    asyncio.run(exercise())


def test_private_methods_and_role_kinds_are_absent(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime, endpoint, adapter = await _graph_runtime(
            tmp_path / "private.sqlite", InMemoryRtgGraph.empty()
        )
        descriptor_fields = {field.name for field in fields(RuntimeActionBindingDescriptor)}
        assert "component_kind" not in descriptor_fields
        assert "handler_kind" not in descriptor_fields
        assert all(
            "_" not in item.action_id.rsplit(".", 1)[-1][:1] for item in adapter.describe().actions
        )
        with pytest.raises(RuntimeActionUnknown):
            await endpoint.request(
                ActionRef(
                    "component.rtg.graph",
                    "component.rtg.graph._private",
                    1,
                    "codec.python.rtg.graph.request.json",
                ),
                {},
                target=runtime.address_for("graph"),
            )
        await runtime.aclose()

    asyncio.run(exercise())


def test_replay_state_operations_are_composed_not_subclassed() -> None:
    state = {"value": 1}
    adapter = ComponentAdapter(
        binding_id="binding.test.state",
        component_contract_id="component.test.state",
        replay_state=ReplayStateBinding(
            is_empty=lambda: state["value"] == 0,
            reset=lambda: state.update(value=0),
            import_checkpoint=lambda _reference: 7,
            export_state=lambda: state,
            verify=lambda: ("problem",) if state["value"] < 0 else (),
        ),
    )

    async def exercise() -> None:
        assert not (await adapter.replay_state_status()).empty
        await adapter.reset_replay_state()
        assert (await adapter.replay_state_status()).empty
        assert await adapter.import_replay_checkpoint("checkpoint") == 7
        assert len(await adapter.replay_state_digest()) == 64
        assert await adapter.verify_replay_state() == ()

    asyncio.run(exercise())


def test_actionless_adapter_requires_explicit_identity() -> None:
    with pytest.raises(RuntimeBindingInvalid):
        ComponentAdapter()


def test_endpoint_continuations_are_awaitable_from_another_event_loop(tmp_path: Path) -> None:
    async def exercise() -> None:
        graph = InMemoryRtgGraph.empty()
        runtime, endpoint, _adapter = await _graph_runtime(
            tmp_path / "cross-loop.sqlite",
            graph,
        )

        async def request_from_foreign_loop() -> RuntimeRequestOutcome:
            return await endpoint.request(
                RTG_GRAPH_ACTIONS["put_anchor"],
                {"anchor": RtgAnchor(None, "Person")},
                target=runtime.address_for("graph"),
            )

        outcome = await asyncio.to_thread(lambda: asyncio.run(request_from_foreign_loop()))
        assert outcome.response.kind.value == "response"
        assert len(graph.export_snapshot().anchors) == 1
        await runtime.aclose()

    asyncio.run(exercise())
