from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from pathlib import Path

import pytest

from components.interface.mcp_gateway import (
    McpGatewayEndpoint,
    McpGatewayInvocation,
    McpGatewayRegistrationInvalid,
    McpGatewayToolRegistration,
    McpGatewayToolUnknown,
    RuntimeMcpGateway,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ComponentEndpoint,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
)
from components.runtime.message_runtime import (
    RuntimeMessageConflict,
    RuntimeReplayMode,
    SqliteMessageRuntime,
)
from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    RuntimeCuratedOperationDeclaration,
    RuntimeLaneDeclaration,
    RuntimePayloadDisposition,
    RuntimeTopologyManifest,
    topology_manifest_hash,
)

MODEL_EVIDENCE = {
    "McpGatewayBoundaryVerification": ("test_gateway_dispatches_only_curated_registered_tools",),
    "RegisterMcpGatewayToolsContractVerification": (
        "test_gateway_registration_validation_is_atomic",
    ),
    "GetMcpGatewayRegistrationsContractVerification": (
        "test_gateway_registration_inventory_is_a_defensive_snapshot",
    ),
    "InvokeMcpGatewayToolContractVerification": (
        "test_gateway_dispatches_only_curated_registered_tools",
    ),
}


def _registration() -> McpGatewayToolRegistration:
    return McpGatewayToolRegistration(
        tool_name="echo",
        description="Echo one string.",
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        annotations={"readOnlyHint": True},
        target_instance_key="facade",
        component_contract_id="application.test.facade",
        action_id="application.test.facade.echo",
        schema_version=1,
        binding_id="binding.test.facade.v1",
        binding_version=1,
        request_codec_id="codec.test.facade.request.json",
        request_codec_version=1,
        request_payload_disposition=RuntimePayloadDisposition.COMMAND,
        result_payload_disposition=RuntimePayloadDisposition.QUERY_RESULT,
        fault_payload_disposition=RuntimePayloadDisposition.DIAGNOSTIC,
    )


def test_gateway_seal_freezes_registration_inventory_and_digest() -> None:
    gateway = RuntimeMcpGateway((_registration(),))
    digest = gateway.seal()
    assert digest == gateway.registration_digest
    assert gateway.seal() == digest
    with pytest.raises(McpGatewayRegistrationInvalid):
        gateway.register_tools((_registration(),))
    assert gateway.registration_digest == digest
    assert tuple(item.tool_name for item in gateway.registrations) == ("echo",)


async def _gateway_runtime(path: Path) -> tuple[SqliteMessageRuntime, McpGatewayEndpoint]:
    registration = _registration()
    gateway = RuntimeMcpGateway((registration,))
    gateway_adapter = gateway.create_adapter()
    descriptor = RuntimeActionBindingDescriptor(
        "application.test.facade",
        "application.test.facade.echo",
        "binding.test.facade.v1",
        1,
        1,
        "codec.test.facade.request.json",
        "codec.test.facade.result.json",
        "codec.test.facade.failure.json",
        RuntimeActionIdempotency.IDEMPOTENT,
        RuntimeReplayMode.NO_STATE_EFFECT,
    )
    facade = ComponentAdapter(
        (
            ActionBinding(
                descriptor,
                lambda payload: ((str(payload["value"]),), {}),
                lambda result: result,
                invoke=lambda value: {"ok": True, "result": {"echo": value}},
            ),
        )
    )
    declarations = (
        ComponentOccurrenceDeclaration(
            "gateway",
            gateway_adapter.describe().component_contract_id,
            gateway_adapter.describe().binding_id,
            1,
            lanes=(RuntimeLaneDeclaration("ingress", worker_limit=2),),
        ),
        ComponentOccurrenceDeclaration(
            "facade",
            facade.describe().component_contract_id,
            facade.describe().binding_id,
            1,
        ),
    )
    manifest = RuntimeTopologyManifest("test.gateway", 4, declarations, (), "")
    manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
    runtime = SqliteMessageRuntime(path, runtime_key="test.gateway")
    await runtime.prepare_static_topology(manifest)
    for declaration, participant in zip(declarations, (gateway_adapter, facade), strict=True):
        occurrence = await runtime.register_occurrence(declaration)
        await runtime.attach_participant(occurrence, participant, participant.describe().actions)
    await runtime.confirm_static_topology(manifest)
    endpoint = ComponentEndpoint(
        runtime,
        gateway_adapter,
        source=runtime.address_for("gateway"),
    )
    return runtime, McpGatewayEndpoint(
        endpoint,
        runtime.address_for,
        gateway,
    )


def test_gateway_dispatches_only_curated_registered_tools(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime, gateway = await _gateway_runtime(tmp_path / "runtime.sqlite")
        outcome = await gateway.invoke_tool(McpGatewayInvocation("echo", {"value": "hi"}))
        assert outcome.result["ok"] is True
        assert outcome.result["result"] == {"echo": "hi"}
        assert outcome.result["runtime"]["message_id"] == str(outcome.message_id)
        with pytest.raises(McpGatewayToolUnknown):
            await gateway.invoke_tool(McpGatewayInvocation("private_method", {}))
        await runtime.aclose()

    asyncio.run(exercise())
    source = inspect.getsource(RuntimeMcpGateway)
    assert "components.rtg" not in source
    assert "controller" not in source.lower()


def test_gateway_request_keys_are_durable_and_conflict_safe(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime, gateway = await _gateway_runtime(tmp_path / "runtime.sqlite")
        invocation = McpGatewayInvocation(
            "echo",
            {"value": "hi", "runtime_options": {"request_key": "agent.step-1"}},
        )
        first = await gateway.invoke_tool(invocation)
        duplicate = await gateway.invoke_tool(invocation)
        assert duplicate.message_id == first.message_id
        assert duplicate.terminal_position == first.terminal_position
        with pytest.raises(RuntimeMessageConflict, match=str(first.message_id)):
            await gateway.invoke_tool(
                McpGatewayInvocation(
                    "echo",
                    {"value": "changed", "runtime_options": {"request_key": "agent.step-1"}},
                )
            )
        await runtime.aclose()

    asyncio.run(exercise())


def test_gateway_routes_registrations_to_distinct_occurrences(tmp_path: Path) -> None:
    async def exercise() -> None:
        first = _registration()
        second = replace(first, tool_name="echo_two", target_instance_key="facade.two")
        gateway = RuntimeMcpGateway((first, second))
        gateway_adapter = gateway.create_adapter()
        descriptor = RuntimeActionBindingDescriptor(
            "application.test.facade",
            "application.test.facade.echo",
            "binding.test.facade.v1",
            1,
            1,
            "codec.test.facade.request.json",
            "codec.test.facade.result.json",
            "codec.test.facade.failure.json",
            RuntimeActionIdempotency.IDEMPOTENT,
            RuntimeReplayMode.NO_STATE_EFFECT,
        )

        def facade(label: str) -> ComponentAdapter:
            return ComponentAdapter(
                (
                    ActionBinding(
                        descriptor,
                        lambda payload: ((str(payload["value"]),), {}),
                        lambda result: result,
                        invoke=lambda value: {
                            "ok": True,
                            "result": {"echo": value, "occurrence": label},
                        },
                    ),
                )
            )

        facade_one = facade("one")
        facade_two = facade("two")
        declarations = (
            ComponentOccurrenceDeclaration(
                "gateway",
                gateway_adapter.describe().component_contract_id,
                gateway_adapter.describe().binding_id,
                1,
                lanes=(RuntimeLaneDeclaration("ingress", worker_limit=2),),
            ),
            ComponentOccurrenceDeclaration(
                "facade",
                facade_one.describe().component_contract_id,
                facade_one.describe().binding_id,
                1,
            ),
            ComponentOccurrenceDeclaration(
                "facade.two",
                facade_two.describe().component_contract_id,
                facade_two.describe().binding_id,
                1,
            ),
        )
        operations = tuple(
            RuntimeCuratedOperationDeclaration(
                operation_id=item.tool_name,
                target_instance_key=item.target_instance_key,
                component_contract_id=item.component_contract_id,
                action_id=item.action_id,
                schema_version=item.schema_version,
                binding_id=item.binding_id,
                binding_version=item.binding_version,
                request_codec_id=item.request_codec_id,
                request_codec_version=item.request_codec_version,
                request_payload_disposition=item.request_payload_disposition,
                result_payload_disposition=item.result_payload_disposition,
                fault_payload_disposition=item.fault_payload_disposition,
                effect_payload_disposition=item.effect_payload_disposition,
            )
            for item in (first, second)
        )
        manifest = RuntimeTopologyManifest("test.gateway.multi", 4, declarations, operations, "")
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        runtime = SqliteMessageRuntime(
            tmp_path / "multi.sqlite",
            runtime_key="test.gateway.multi",
        )
        await runtime.prepare_static_topology(manifest)
        for declaration, participant in zip(
            declarations,
            (gateway_adapter, facade_one, facade_two),
            strict=True,
        ):
            occurrence = await runtime.register_occurrence(declaration)
            await runtime.attach_participant(
                occurrence,
                participant,
                participant.describe().actions,
            )
        await runtime.confirm_static_topology(manifest)
        endpoint = McpGatewayEndpoint(
            ComponentEndpoint(
                runtime,
                gateway_adapter,
                source=runtime.address_for("gateway"),
            ),
            runtime.address_for,
            gateway,
        )
        one = await endpoint.invoke_tool(McpGatewayInvocation("echo", {"value": "a"}))
        two = await endpoint.invoke_tool(McpGatewayInvocation("echo_two", {"value": "b"}))
        assert one.result["result"]["occurrence"] == "one"  # type: ignore[index]
        assert two.result["result"]["occurrence"] == "two"  # type: ignore[index]
        await runtime.aclose()

    asyncio.run(exercise())


def test_gateway_registration_validation_is_atomic() -> None:
    registration = _registration()
    gateway = RuntimeMcpGateway((registration,))
    original = gateway.registrations
    with pytest.raises(McpGatewayRegistrationInvalid):
        gateway.register_tools((registration, registration))
    assert gateway.registrations == original


def test_gateway_registration_inventory_is_a_defensive_snapshot() -> None:
    registration = _registration()
    gateway = RuntimeMcpGateway((registration,))
    first = gateway.registrations
    second = gateway.registrations
    assert first == second == (registration,)
    assert first is not second
