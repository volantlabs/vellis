from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from components.runtime.message_runtime.protocol import JsonObject


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
    codec_id: str
    codec_version: int


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

    def register_tools(self, registrations: tuple[McpGatewayToolRegistration, ...]) -> None:
        """Replace the curated tool registration inventory."""
        ...

    async def invoke_tool(self, invocation: McpGatewayInvocation) -> McpGatewayOutcome:
        """Validate and dispatch one curated tool invocation."""
        ...
