from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from components.runtime.message_runtime.protocol import JsonObject
from components.runtime.messaging import RuntimePayloadDisposition, RuntimeTraceDisposition


@dataclass(frozen=True, slots=True)
class McpGatewayToolRegistration:
    tool_name: str
    description: str
    parameter_schema: JsonObject
    annotations: JsonObject
    target_instance_key: str
    component_contract_id: str
    action_id: str
    schema_version: int
    binding_id: str
    binding_version: int
    request_codec_id: str
    request_codec_version: int
    request_payload_disposition: RuntimePayloadDisposition
    result_payload_disposition: RuntimePayloadDisposition
    fault_payload_disposition: RuntimePayloadDisposition
    effect_payload_disposition: RuntimePayloadDisposition | None = None


@dataclass(frozen=True, slots=True)
class McpGatewayInvocation:
    tool_name: str
    arguments: JsonObject


@dataclass(frozen=True, slots=True)
class McpGatewayOutcome:
    tool_name: str
    result: JsonObject
    message_id: UUID
    trace_id: UUID
    terminal_position: int
    trace_disposition: RuntimeTraceDisposition


class McpGatewayRegistrationInvalid(Exception):
    """The curated tool registration set is invalid."""


class McpGatewayToolUnknown(Exception):
    """No curated tool registration has the requested name."""


class McpGatewayInvocationInvalid(Exception):
    """The invocation arguments do not satisfy the registered tool schema."""


class McpGateway(Protocol):
    @property
    def registrations(self) -> tuple[McpGatewayToolRegistration, ...]:
        """Return the current curated tool inventory."""
        ...

    async def invoke_tool(self, invocation: McpGatewayInvocation) -> McpGatewayOutcome:
        """Validate and dispatch one curated tool invocation."""
        ...


class ConfigurableMcpGateway(McpGateway, Protocol):
    def register_tools(self, registrations: tuple[McpGatewayToolRegistration, ...]) -> None:
        """Replace the curated inventory before the gateway is sealed and attached."""
        ...
