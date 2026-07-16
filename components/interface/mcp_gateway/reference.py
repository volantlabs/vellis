from __future__ import annotations

from components.interface.mcp_gateway import (
    McpGatewayToolRegistration,
    RuntimeMcpGateway,
)
from components.runtime.messaging import RuntimePayloadDisposition


def create_reference_component() -> RuntimeMcpGateway:
    return RuntimeMcpGateway(
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
                binding_id="binding.reference.facade.v1",
                binding_version=1,
                request_codec_id="codec.reference.facade.request.json",
                request_codec_version=1,
                request_payload_disposition=RuntimePayloadDisposition.COMMAND,
                result_payload_disposition=RuntimePayloadDisposition.QUERY_RESULT,
                fault_payload_disposition=RuntimePayloadDisposition.DIAGNOSTIC,
            ),
        )
    )


def run_reference() -> tuple[str, ...]:
    return tuple(item.tool_name for item in create_reference_component().registrations)


if __name__ == "__main__":
    print(run_reference())
