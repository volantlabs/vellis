from __future__ import annotations

from tempfile import TemporaryDirectory

from components.interface.mcp_gateway import (
    McpGatewayInvocation,
    McpGatewayToolRegistration,
    RuntimeMcpGateway,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ExplicitComponentAdapter,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import RuntimeReplayMode, SqliteMessageRuntime


def run_reference() -> dict[str, object]:
    """Map one curated tool to one runtime action."""
    descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="application.reference.facade",
        action_id="application.reference.facade.echo",
        binding_id="binding.reference.facade.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.reference.facade.request.json",
        result_codec_id="codec.reference.facade.result.json",
        failure_codec_id="codec.reference.facade.failure.json",
        idempotency=RuntimeActionIdempotency.IDEMPOTENT,
        replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
    )
    adapter = ExplicitComponentAdapter(
        (
            ActionBinding(
                descriptor=descriptor,
                invoke=lambda value: {"ok": True, "result": {"echo": value}},
                decode_request=lambda payload: ((str(payload["value"]),), {}),
                encode_result=encode_json,
            ),
        )
    )
    with TemporaryDirectory() as directory:
        with SqliteMessageRuntime.open(
            f"{directory}/runtime.sqlite", runtime_key="gateway.reference"
        ) as runtime:
            runtime.register_source_occurrence(
                instance_key="reference.interface.mcp",
                component_contract_id="component.interface.mcp_gateway",
                binding_id="binding.reference.mcp.source.v1",
            )
            runtime.register_adapter(
                instance_key="reference.facade.primary",
                component_contract_id="application.reference.facade",
                adapter=adapter,
            )
            gateway = RuntimeMcpGateway(runtime, source_instance_key="reference.interface.mcp")
            gateway.register_tools(
                (
                    McpGatewayToolRegistration(
                        tool_name="echo",
                        description="Echo one string.",
                        parameter_schema={
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                            "additionalProperties": False,
                        },
                        annotations={"readOnlyHint": True},
                        target_instance_key="reference.facade.primary",
                        component_contract_id="application.reference.facade",
                        action_id="application.reference.facade.echo",
                        schema_version=1,
                        codec_id="codec.reference.facade.request.json",
                        codec_version=1,
                    ),
                )
            )
            return dict(
                gateway.invoke_tool_sync(
                    McpGatewayInvocation(tool_name="echo", arguments={"value": "hello"})
                ).result
            )


if __name__ == "__main__":
    print(run_reference())
