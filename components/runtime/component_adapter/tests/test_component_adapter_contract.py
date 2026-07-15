from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

import pytest

from components.rtg.graph import InMemoryRtgGraph, RtgAnchor, RtgGraphObjectNotFound
from components.rtg.graph.runtime_binding import create_rtg_graph_adapter, create_rtg_graph_proxy
from components.runtime.component_adapter import (
    ActionBinding,
    ExplicitComponentAdapter,
    MethodBindingSpec,
    MutableAdapterHost,
    ReplayStateBinding,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeBindingInvalid,
    create_typed_component_adapter,
    create_typed_proxy,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import (
    JsonObject,
    RuntimeHistoryQuery,
    RuntimeReplayMode,
    RuntimeTraceDisposition,
    SqliteMessageRuntime,
)

MODEL_EVIDENCE = {
    "ComponentRuntimeAdapterBoundaryVerification": (
        "test_graph_direct_and_message_invocation_are_equivalent",
        "test_generated_identity_is_captured_in_canonical_effect",
        "test_private_or_unregistered_methods_are_not_routable",
        "test_recovery_authorization_is_limited_to_non_effectful_coordinators",
        "test_standard_bibliotek_bindings_preserve_direct_protocol",
    ),
    "DescribeRuntimeBindingContractVerification": (
        "test_private_or_unregistered_methods_are_not_routable",
        "test_descriptor_is_complete_and_mutable_host_keeps_proxy_address_stable",
    ),
    "DispatchRuntimeMessageContractVerification": (
        "test_graph_direct_and_message_invocation_are_equivalent",
        "test_modeled_fault_can_record_and_apply_its_documented_effect",
    ),
    "ApplyCanonicalReplayEffectContractVerification": (
        "test_generated_identity_is_captured_in_canonical_effect",
        "test_canonical_effect_rejects_changed_contract_or_message_schema",
        "test_modeled_fault_can_record_and_apply_its_documented_effect",
    ),
    "ReplayStateStatusContractVerification": ("test_replay_state_spi_is_explicit",),
    "ResetReplayStateContractVerification": ("test_replay_state_spi_is_explicit",),
    "ImportReplayCheckpointContractVerification": ("test_replay_state_spi_is_explicit",),
    "ReplayStateDigestContractVerification": ("test_replay_state_spi_is_explicit",),
    "VerifyReplayStateContractVerification": ("test_replay_state_spi_is_explicit",),
}


class _AdderProtocol(Protocol):
    def add(self, value: int = 2) -> int: ...


class _Adder:
    def __init__(self, base: int) -> None:
        self.base = base

    def add(self, value: int = 2) -> int:
        return self.base + value


class _RecordedFailure(ValueError):
    pass


class _UnrecordedFailure(ValueError):
    pass


class _FailingStateProtocol(Protocol):
    def fail_after_setting(self, value: int) -> None: ...


class _FailingState:
    def __init__(self) -> None:
        self.value = 0

    def fail_after_setting(self, value: int) -> None:
        if value < 0:
            raise _UnrecordedFailure("the rejected request has no state effect")
        self.value = value
        raise _RecordedFailure("the documented failure retains state")


def _build_recorded_failure_effect(component: object, error: Exception) -> JsonObject:
    assert isinstance(component, _FailingState)
    assert isinstance(error, _RecordedFailure)
    return {"supersedes_trace_effects": True, "value": component.value}


def _apply_recorded_failure_effect(component: object, payload: JsonObject) -> None:
    assert isinstance(component, _FailingState)
    value = payload.get("value")
    if not isinstance(value, int):
        raise ValueError("recorded failure effect requires an integer value")
    component.value = value


def _proxy_pair(tmp_path: Path):
    runtime = SqliteMessageRuntime.open(tmp_path / "runtime.sqlite", runtime_key="test.adapter")
    graph = InMemoryRtgGraph.empty()
    adapter = create_rtg_graph_adapter(graph)
    registration = runtime.register_adapter(
        instance_key="test.graph.primary",
        component_contract_id="component.rtg.graph",
        adapter=adapter,
    )
    address = runtime.address_for(registration.instance_key)
    return runtime, graph, adapter, create_rtg_graph_proxy(runtime, address, address)


def test_graph_direct_and_message_invocation_are_equivalent(tmp_path: Path) -> None:
    runtime, graph, _, proxy = _proxy_pair(tmp_path)
    try:
        request = RtgAnchor(None, "test.person", display_name="Ada")
        stored = proxy.put_anchor(request)
        assert stored.uuid is not None
        assert proxy.get_object(stored.uuid) == graph.get_object(stored.uuid)
        with pytest.raises(RtgGraphObjectNotFound):
            proxy.get_object("00000000-0000-0000-0000-000000000000")
    finally:
        runtime.close()


def test_standard_bibliotek_bindings_preserve_direct_protocol(tmp_path: Path) -> None:
    from components.runtime.component_adapter.tests import (
        test_standard_binding_conformance as standard_conformance,
    )

    standard_conformance.assert_standard_binding_conformance(tmp_path)


def test_generated_identity_is_captured_in_canonical_effect(tmp_path: Path) -> None:
    runtime, _, _, proxy = _proxy_pair(tmp_path)
    try:
        stored = proxy.put_anchor(RtgAnchor(None, "test.generated"))
        facts = runtime.query_history_sync(
            RuntimeHistoryQuery(action_id="component.rtg.graph.put_anchor")
        )
        effect = next(fact for fact in facts.facts if fact.fact_type == "canonical_effect")
        encoded = effect.details["effect"]
        assert isinstance(encoded, dict)
        payload = encoded["payload"]
        assert isinstance(payload, dict)
        anchor = payload["anchor"]
        assert isinstance(anchor, dict)
        assert anchor["uuid"] == str(stored.uuid)
    finally:
        runtime.close()


def test_modeled_fault_can_record_and_apply_its_documented_effect(tmp_path: Path) -> None:
    state = _FailingState()
    specs = (
        MethodBindingSpec(
            method_name="fail_after_setting",
            replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
            idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
            modeled_fault_trace_disposition=RuntimeTraceDisposition.COMMITTED,
            failure_replay_effect_builder=_build_recorded_failure_effect,
            failure_replay_effect_applier=_apply_recorded_failure_effect,
            failure_types=(_RecordedFailure, _UnrecordedFailure),
            failure_trace_dispositions=(
                (_UnrecordedFailure, RuntimeTraceDisposition.ABORTED),
            ),
            failure_replay_effect_types=(_RecordedFailure,),
        ),
    )
    adapter = create_typed_component_adapter(
        state,
        _FailingStateProtocol,
        component_contract_id="component.test.failing_state",
        binding_id="binding.test.failing_state.v1",
        specs=specs,
        failure_types=(_RecordedFailure, _UnrecordedFailure),
    )
    runtime = SqliteMessageRuntime.open(tmp_path / "failure.sqlite", runtime_key="test.failure")
    registration = runtime.register_adapter(
        instance_key="test.failing_state.primary",
        component_contract_id="component.test.failing_state",
        adapter=adapter,
    )
    address = runtime.address_for(registration.instance_key)
    proxy = create_typed_proxy(
        runtime,
        address,
        address,
        _FailingStateProtocol,
        component_contract_id="component.test.failing_state",
        specs=specs,
        failure_types=(_RecordedFailure, _UnrecordedFailure),
    )
    try:
        with pytest.raises(_UnrecordedFailure):
            proxy.fail_after_setting(-1)
        assert state.value == 0
        assert not runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect")
        ).facts
        assert runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="trace_aborted")
        ).facts

        with pytest.raises(_RecordedFailure):
            proxy.fail_after_setting(7)
        effect_fact = runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect")
        ).facts[0]
        effect = effect_fact.details["effect"]
        assert isinstance(effect, dict)
        payload = effect["payload"]
        assert isinstance(payload, dict)
        assert payload["supersedes_trace_effects"] is True

        reconstructed = _FailingState()
        reconstructed_adapter = create_typed_component_adapter(
            reconstructed,
            _FailingStateProtocol,
            component_contract_id="component.test.failing_state",
            binding_id="binding.test.failing_state.v1",
            specs=specs,
            failure_types=(_RecordedFailure, _UnrecordedFailure),
        )
        asyncio.run(reconstructed_adapter.apply_replay_effect(effect))
        assert reconstructed.value == 7
    finally:
        runtime.close()


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("component_contract_id", "component.rtg.schema"),
        ("schema_version", 2),
    ),
)
def test_canonical_effect_rejects_changed_contract_or_message_schema(
    tmp_path: Path,
    field: str,
    changed: object,
) -> None:
    runtime, _, adapter, proxy = _proxy_pair(tmp_path)
    try:
        proxy.put_anchor(RtgAnchor(None, "test.generated"))
        facts = runtime.query_history_sync(
            RuntimeHistoryQuery(
                action_id="component.rtg.graph.put_anchor",
                fact_type="canonical_effect",
            )
        )
        encoded = facts.facts[0].details["effect"]
        assert isinstance(encoded, dict)
        incompatible = {**encoded, field: changed}

        with pytest.raises(RuntimeBindingInvalid, match="contract/schema mismatch"):
            asyncio.run(adapter.apply_replay_effect(incompatible))
    finally:
        runtime.close()


def test_private_or_unregistered_methods_are_not_routable(tmp_path: Path) -> None:
    runtime, _, adapter, _ = _proxy_pair(tmp_path)
    try:
        actions = {action.action_id for action in adapter.describe().actions}
        assert "component.rtg.graph._normalize_anchor" not in actions
        with pytest.raises(RuntimeBindingInvalid):
            # Adapter validation occurs before any target method lookup.
            import asyncio

            from components.runtime.component_adapter.implementation import RuntimeClient

            address = runtime.address_for("test.graph.primary")
            client = RuntimeClient(
                runtime,
                source=address,
                target=address,
                component_contract_id="component.rtg.graph",
                request_codec_id="codec.python.rtg.graph.request.json",
            )
            asyncio.run(adapter.dispatch(client.envelope("component.rtg.graph.private", {})))
    finally:
        runtime.close()


def test_descriptor_is_complete_and_mutable_host_keeps_proxy_address_stable(
    tmp_path: Path,
) -> None:
    host: MutableAdapterHost[object] = MutableAdapterHost(_Adder(10))
    specs = (
        MethodBindingSpec(
            method_name="add",
            replay_mode=RuntimeReplayMode.CANONICAL_EFFECT,
            idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
        ),
    )
    adapter = create_typed_component_adapter(
        host,
        _AdderProtocol,
        component_contract_id="component.test.adder",
        binding_id="binding.test.adder.v1",
        specs=specs,
        failure_types=(ValueError,),
    )
    descriptor = adapter.describe().actions[0]
    assert descriptor.request_codec_version == 1
    assert descriptor.result_codec_version == 1
    assert descriptor.failure_codec_version == 1
    assert descriptor.supported_failure_names == ("ValueError",)
    assert descriptor.failure_bindings[0].failure_name == "ValueError"
    assert descriptor.failure_bindings[0].codec_version == 1
    assert descriptor.request_arguments[0].name == "value"
    assert descriptor.request_arguments[0].default == 2
    assert descriptor.canonical_effect_schema_version == 1
    assert descriptor.canonical_effect_codec_version == 1
    assert descriptor.canonical_effect_codec_id

    runtime = SqliteMessageRuntime.open(tmp_path / "host.sqlite", runtime_key="test.host")
    registration = runtime.register_adapter(
        instance_key="test.adder.primary",
        component_contract_id="component.test.adder",
        adapter=adapter,
    )
    address = runtime.address_for(registration.instance_key)
    proxy = create_typed_proxy(
        runtime,
        address,
        address,
        _AdderProtocol,
        component_contract_id="component.test.adder",
        specs=specs,
        failure_types=(ValueError,),
    )
    try:
        assert proxy.add() == 12
        host.replace(_Adder(20))
        assert proxy.add() == 22
        assert runtime.address_for("test.adder.primary") == address
    finally:
        runtime.close()


def test_recovery_authorization_is_limited_to_non_effectful_coordinators() -> None:
    descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.recovery",
        action_id="component.test.recovery.run",
        binding_id="binding.test.recovery.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.recovery.request.json",
        result_codec_id="codec.test.recovery.result.json",
        failure_codec_id="codec.test.recovery.failure.json",
        idempotency=RuntimeActionIdempotency.IDEMPOTENT,
        replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
        externally_effectful=True,
        recovery_authorized=True,
    )

    with pytest.raises(
        RuntimeBindingInvalid,
        match="recovery-authorized actions must be non-effectful coordinator actions",
    ):
        ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=descriptor,
                    invoke=lambda: None,
                    decode_request=lambda _payload: ((), {}),
                    encode_result=encode_json,
                ),
            )
        )


def test_replay_state_spi_is_explicit() -> None:
    state = {"value": 3}

    def reset() -> None:
        state["value"] = 0

    def import_checkpoint(reference: str) -> int:
        cursor, value = reference.split(":")
        state["value"] = int(value)
        return int(cursor)

    descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.state",
        action_id="component.test.state.read",
        binding_id="binding.test.state.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.state.request.json",
        result_codec_id="codec.test.state.result.json",
        failure_codec_id="codec.test.state.failure.json",
        idempotency=RuntimeActionIdempotency.IDEMPOTENT,
        replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
    )
    adapter = ExplicitComponentAdapter(
        (
            ActionBinding(
                descriptor=descriptor,
                invoke=lambda: state["value"],
                decode_request=lambda _payload: ((), {}),
                encode_result=encode_json,
            ),
        ),
        replay_state=ReplayStateBinding(
            is_empty=lambda: state["value"] == 0,
            reset=reset,
            import_checkpoint=import_checkpoint,
            export_state=lambda: dict(state),
            verify=lambda: (),
        ),
    )

    async def exercise() -> None:
        assert not (await adapter.replay_state_status()).empty
        await adapter.reset_replay_state()
        assert (await adapter.replay_state_status()).empty
        assert await adapter.import_replay_checkpoint("7:4") == 7
        assert len(await adapter.replay_state_digest()) == 64
        assert await adapter.verify_replay_state() == ()

    asyncio.run(exercise())
