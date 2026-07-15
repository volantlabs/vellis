from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from components.interface.mcp_gateway import (
    McpGatewayInvocation,
    McpGatewayInvocationInvalid,
    McpGatewayRegistrationInvalid,
    McpGatewayToolRegistration,
    McpGatewayToolUnknown,
    RuntimeMcpGateway,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ExplicitComponentAdapter,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import (
    JsonObject,
    RuntimeActionUnknown,
    RuntimeAddress,
    RuntimeAddressUnknown,
    RuntimeError,
    RuntimeFailStopped,
    RuntimeLedgerUnavailable,
    RuntimeMessageConflict,
    RuntimeMessageEnvelope,
    RuntimeQueueFull,
    RuntimeRegistrationInvalid,
    RuntimeReplayMode,
    RuntimeRequestOutcome,
    RuntimeRequestTimedOut,
    RuntimeSchemaUnsupported,
    RuntimeTraceDisposition,
    SqliteMessageRuntime,
)

MODEL_EVIDENCE = {
    "McpGatewayBoundaryVerification": (
        "test_gateway_dispatches_only_curated_registered_tools",
    ),
    "RegisterMcpGatewayToolsContractVerification": (
        "test_gateway_registration_validation_is_atomic",
    ),
    "GetMcpGatewayRegistrationsContractVerification": (
        "test_gateway_registration_inventory_is_a_defensive_snapshot",
    ),
    "InvokeMcpGatewayToolContractVerification": (
        "test_gateway_dispatches_only_curated_registered_tools",
        "test_gateway_promotes_modeled_fault_evidence_into_the_external_envelope",
        "test_gateway_validates_arguments_before_dispatch",
        "test_gateway_propagates_runtime_failures_without_retyping",
    ),
}


class _Counter:
    def __init__(self) -> None:
        self.value = 0
        self.calls = 0

    def increment(self, amount: int) -> int:
        self.calls += 1
        self.value += amount
        return self.value


class _ModeledFailure(Exception):
    def __init__(self) -> None:
        self.diagnostic = {"code": "test.modeled_failure"}
        self.validation_report = {"accepted": False, "findings": [{"code": "blocked"}]}
        self.transaction_id = "legacy-transaction"
        super().__init__("modeled target failure")


class _ForwardingRuntime:
    """Structural gateway seam that deliberately is not a concrete runtime subtype."""

    def __init__(self, runtime: SqliteMessageRuntime) -> None:
        self._runtime = runtime

    def address_for(self, instance_key: str) -> RuntimeAddress:
        return self._runtime.address_for(instance_key)

    async def request(
        self,
        message: RuntimeMessageEnvelope,
        timeout_seconds: float | None = None,
    ) -> RuntimeRequestOutcome:
        return await self._runtime.request(message, timeout_seconds)


def _counter_adapter(counter: _Counter) -> ExplicitComponentAdapter:
    return ExplicitComponentAdapter(
        (
            ActionBinding(
                descriptor=RuntimeActionBindingDescriptor(
                    component_contract_id="component.test.counter",
                    action_id="component.test.counter.increment",
                    binding_id="binding.test.counter.v1",
                    binding_version=1,
                    schema_version=1,
                    request_codec_id="codec.test.counter.request.json",
                    result_codec_id="codec.test.counter.result.json",
                    failure_codec_id="codec.test.counter.failure.json",
                    idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
                    replay_mode=RuntimeReplayMode.CANONICAL_EFFECT,
                ),
                invoke=counter.increment,
                decode_request=lambda payload: ((cast(int, payload["amount"]),), {}),
                encode_result=encode_json,
                build_replay_effect=lambda args, _kwargs, _result: {"amount": cast(int, args[0])},
                apply_replay_effect=lambda payload: counter.increment(cast(int, payload["amount"])),
            ),
        )
    )


def _gateway(tmp_path: Path) -> tuple[SqliteMessageRuntime, _Counter, RuntimeMcpGateway]:
    runtime = SqliteMessageRuntime.open(tmp_path / "runtime.sqlite", runtime_key="test.gateway")
    counter = _Counter()
    runtime.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(counter),
    )
    gateway = RuntimeMcpGateway(
        _ForwardingRuntime(runtime), source_instance_key="test.counter.primary"
    )
    gateway.register_tools(
        (
            McpGatewayToolRegistration(
                tool_name="increment_counter",
                description="Increment the registered test counter.",
                parameter_schema={
                    "type": "object",
                    "properties": {"amount": {"type": "integer"}},
                    "required": ["amount"],
                    "additionalProperties": False,
                },
                annotations={"readOnlyHint": False},
                target_instance_key="test.counter.primary",
                component_contract_id="component.test.counter",
                action_id="component.test.counter.increment",
                schema_version=1,
                codec_id="codec.test.counter.request.json",
                codec_version=1,
            ),
        )
    )
    return runtime, counter, gateway


@pytest.mark.parametrize(
    "runtime_error",
    (
        RuntimeRegistrationInvalid("invalid causal registration"),
        RuntimeAddressUnknown("unknown target"),
        RuntimeActionUnknown("unknown action"),
        RuntimeSchemaUnsupported("unsupported schema"),
        RuntimeMessageConflict("message identity conflict"),
        RuntimeQueueFull("target queue full"),
        RuntimeLedgerUnavailable("ledger unavailable"),
        RuntimeFailStopped("runtime recovery required"),
        RuntimeRequestTimedOut(uuid4()),
    ),
    ids=(
        "registration",
        "address",
        "action",
        "schema",
        "message-conflict",
        "queue",
        "ledger",
        "fail-stop",
        "timeout",
    ),
)
def test_gateway_propagates_runtime_failures_without_retyping(
    runtime_error: RuntimeError,
) -> None:
    address = RuntimeAddress(runtime_id=uuid4(), instance_id=uuid4())

    class _FailingRuntime:
        def address_for(self, instance_key: str) -> RuntimeAddress:
            del instance_key
            return address

        async def request(
            self,
            message: RuntimeMessageEnvelope,
            timeout_seconds: float | None = None,
        ) -> RuntimeRequestOutcome:
            del message, timeout_seconds
            raise runtime_error

    gateway = RuntimeMcpGateway(_FailingRuntime(), source_instance_key="test.gateway.primary")
    gateway.register_tools(
        (
            McpGatewayToolRegistration(
                tool_name="invoke_target",
                description="Invoke the target through a deliberately failing runtime.",
                parameter_schema={"type": "object", "additionalProperties": False},
                annotations={"readOnlyHint": True},
                target_instance_key="test.target.primary",
                component_contract_id="component.test.target",
                action_id="component.test.target.invoke",
                schema_version=1,
                codec_id="codec.test.target.request.json",
                codec_version=1,
            ),
        )
    )

    with pytest.raises(type(runtime_error)) as captured:
        asyncio.run(gateway.invoke_tool(McpGatewayInvocation("invoke_target", {})))

    assert captured.value is runtime_error


def test_gateway_dispatches_only_curated_registered_tools(tmp_path: Path) -> None:
    runtime, counter, gateway = _gateway(tmp_path)
    try:
        outcome = asyncio.run(
            gateway.invoke_tool(McpGatewayInvocation("increment_counter", {"amount": 2}))
        )
        assert outcome.result == {"value": 2}
        assert counter.value == 2
        with pytest.raises(McpGatewayToolUnknown):
            asyncio.run(gateway.invoke_tool(McpGatewayInvocation("arbitrary", {})))
    finally:
        runtime.close()


def test_gateway_promotes_modeled_fault_evidence_into_the_external_envelope(
    tmp_path: Path,
) -> None:
    runtime = SqliteMessageRuntime.open(
        tmp_path / "runtime.sqlite",
        runtime_key="test.gateway.fault",
    )

    def fail() -> None:
        raise _ModeledFailure()

    descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.failure",
        action_id="component.test.failure.invoke",
        binding_id="binding.test.failure.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.failure.request.json",
        result_codec_id="codec.test.failure.result.json",
        failure_codec_id="codec.test.failure.failure.json",
        idempotency=RuntimeActionIdempotency.IDEMPOTENT,
        replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
    )
    registration = runtime.register_adapter(
        instance_key="test.failure.primary",
        component_contract_id="component.test.failure",
        adapter=ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=descriptor,
                    invoke=fail,
                    decode_request=lambda _payload: ((), {}),
                    encode_result=encode_json,
                    failure_types=(_ModeledFailure,),
                ),
            )
        ),
    )
    gateway = RuntimeMcpGateway(runtime, source_instance_key=registration.instance_key)
    gateway.register_tools(
        (
            McpGatewayToolRegistration(
                tool_name="invoke_failure",
                description="Invoke a modeled failure for envelope verification.",
                parameter_schema={"type": "object", "additionalProperties": False},
                annotations={"readOnlyHint": True},
                target_instance_key=registration.instance_key,
                component_contract_id="component.test.failure",
                action_id="component.test.failure.invoke",
                schema_version=1,
                codec_id="codec.test.failure.request.json",
                codec_version=1,
            ),
        )
    )
    try:
        outcome = gateway.invoke_tool_sync(McpGatewayInvocation("invoke_failure", {}))

        assert outcome.result == {
            "ok": False,
            "error": {
                "type": "_ModeledFailure",
                "message": "modeled target failure",
                "diagnostic": {"code": "test.modeled_failure"},
            },
            "validation_report": {
                "accepted": False,
                "findings": [{"code": "blocked"}],
            },
            "transaction_id": "legacy-transaction",
        }
        assert runtime.get_trace_sync(outcome.trace_id).disposition is (
            RuntimeTraceDisposition.ABORTED
        )
    finally:
        runtime.close()


def test_gateway_validates_arguments_before_dispatch(tmp_path: Path) -> None:
    runtime, counter, gateway = _gateway(tmp_path)
    try:
        with pytest.raises(McpGatewayInvocationInvalid):
            asyncio.run(
                gateway.invoke_tool(McpGatewayInvocation("increment_counter", {"amount": "2"}))
            )
        assert counter.calls == 0
    finally:
        runtime.close()


def test_gateway_registration_validation_is_atomic(tmp_path: Path) -> None:
    runtime, counter, gateway = _gateway(tmp_path)
    try:
        before = gateway.registrations
        registration = before[0]
        invalid_registrations = (
            replace(registration, target_instance_key=""),
            replace(registration, action_id=" "),
            replace(registration, codec_id=""),
            replace(registration, parameter_schema=cast(JsonObject, [])),
            replace(
                registration,
                parameter_schema={
                    "type": "array",
                    "items": {"type": "integer"},
                },
            ),
            replace(
                registration,
                parameter_schema={
                    "type": "object",
                    "properties": [],
                },
            ),
            replace(registration, annotations={"readOnlyHint": "yes"}),
        )

        for index, invalid in enumerate(invalid_registrations):
            valid_first = replace(registration, tool_name=f"replacement_{index}")
            invalid = replace(invalid, tool_name=f"invalid_{index}")
            with pytest.raises(McpGatewayRegistrationInvalid):
                gateway.register_tools((valid_first, invalid))
            assert gateway.registrations == before

        outcome = asyncio.run(
            gateway.invoke_tool(McpGatewayInvocation("increment_counter", {"amount": 3}))
        )
        assert outcome.result == {"value": 3}
        assert counter.calls == 1
    finally:
        runtime.close()


def test_gateway_registration_inventory_is_a_defensive_snapshot(tmp_path: Path) -> None:
    runtime, _counter, gateway = _gateway(tmp_path)
    try:
        snapshot = gateway.registrations
        snapshot[0].parameter_schema["title"] = "caller mutation"
        snapshot[0].annotations["readOnlyHint"] = True

        current = gateway.registrations
        assert tuple(item.tool_name for item in current) == ("increment_counter",)
        assert "title" not in current[0].parameter_schema
        assert current[0].annotations == {"readOnlyHint": False}
    finally:
        runtime.close()
