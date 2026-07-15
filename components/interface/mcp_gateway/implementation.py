from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace
from typing import Protocol, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from components.interface.mcp_gateway.protocol import (
    McpGatewayInvocation,
    McpGatewayInvocationInvalid,
    McpGatewayOutcome,
    McpGatewayRegistrationInvalid,
    McpGatewayToolRegistration,
    McpGatewayToolUnknown,
)
from components.runtime.component_adapter.implementation import RuntimeClient
from components.runtime.message_runtime.protocol import (
    JsonObject,
    JsonValue,
    MessageRuntime,
    RuntimeAddress,
    RuntimeMessageEnvelope,
    RuntimeMessageKind,
    RuntimeRequestOutcome,
)


class _GatewayRuntime(Protocol):
    """Small runtime seam needed by the gateway's message client."""

    def address_for(self, instance_key: str) -> RuntimeAddress: ...

    async def request(
        self,
        message: RuntimeMessageEnvelope,
        timeout_seconds: float | None = None,
    ) -> RuntimeRequestOutcome: ...


class RuntimeMcpGateway:
    """Curated MCP-to-runtime mapping independent of application implementations."""

    def __init__(
        self,
        runtime: _GatewayRuntime,
        *,
        source_instance_key: str,
        timeout_seconds: float | None = None,
    ) -> None:
        self._runtime = runtime
        self._source_instance_key = source_instance_key
        self._timeout_seconds = timeout_seconds
        self._registrations: dict[str, McpGatewayToolRegistration] = {}

    @property
    def registrations(self) -> tuple[McpGatewayToolRegistration, ...]:
        """Return a defensive snapshot of the curated registration inventory."""
        return tuple(_copy_registration(item) for item in self._registrations.values())

    def register_tools(self, registrations: tuple[McpGatewayToolRegistration, ...]) -> None:
        if not registrations:
            raise McpGatewayRegistrationInvalid("at least one curated tool is required")
        by_name: dict[str, McpGatewayToolRegistration] = {}
        for registration in registrations:
            normalized = _validated_registration(registration)
            if normalized.tool_name in by_name:
                raise McpGatewayRegistrationInvalid(
                    f"duplicate tool registration: {normalized.tool_name}"
                )
            by_name[normalized.tool_name] = normalized
        self._registrations = by_name

    async def invoke_tool(self, invocation: McpGatewayInvocation) -> McpGatewayOutcome:
        registration = self._registration_for(invocation)
        client = self._client_for(registration)
        outcome = await client.request(
            registration.action_id,
            invocation.arguments,
            timeout_seconds=self._timeout_seconds,
        )
        return _gateway_outcome(invocation, outcome)

    def invoke_tool_sync(self, invocation: McpGatewayInvocation) -> McpGatewayOutcome:
        """Validate and dispatch from a synchronous transport such as FastMCP."""
        registration = self._registration_for(invocation)
        outcome = self._client_for(registration).request_sync(
            registration.action_id,
            invocation.arguments,
            timeout_seconds=self._timeout_seconds,
        )
        return _gateway_outcome(invocation, outcome)

    def _registration_for(self, invocation: McpGatewayInvocation) -> McpGatewayToolRegistration:
        registration = self._registrations.get(invocation.tool_name)
        if registration is None:
            raise McpGatewayToolUnknown(invocation.tool_name)
        _validate_arguments(invocation.arguments, registration.parameter_schema)
        return registration

    def _client_for(self, registration: McpGatewayToolRegistration) -> RuntimeClient:
        return RuntimeClient(
            cast(MessageRuntime, self._runtime),
            source=self._runtime.address_for(self._source_instance_key),
            target=self._runtime.address_for(registration.target_instance_key),
            component_contract_id=registration.component_contract_id,
            request_codec_id=registration.codec_id,
            codec_version=registration.codec_version,
            schema_version=registration.schema_version,
        )


def _gateway_outcome(
    invocation: McpGatewayInvocation, outcome: RuntimeRequestOutcome
) -> McpGatewayOutcome:
    payload = outcome.response.payload.value
    if not isinstance(payload, dict):
        raise McpGatewayInvocationInvalid("target response payload is not a JSON object")
    result: JsonObject
    if outcome.response.kind is RuntimeMessageKind.FAULT:
        result = _external_fault_result(cast(JsonObject, payload))
    else:
        encoded = payload.get("result")
        if isinstance(encoded, dict):
            result = cast(JsonObject, encoded)
        else:
            result = {"value": cast(JsonValue, encoded)}
    return McpGatewayOutcome(
        tool_name=invocation.tool_name,
        result=result,
        message_id=outcome.request.message_id,
        trace_id=outcome.request.trace_id,
    )


def _external_fault_result(payload: JsonObject) -> JsonObject:
    """Restore the transport envelope while keeping runtime fault evidence generic."""

    error = {key: value for key, value in payload.items() if key != "evidence"}
    result: JsonObject = {"ok": False, "error": cast(JsonValue, error)}
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        return result
    for key, value in evidence.items():
        if key == "diagnostic":
            error[key] = value
        else:
            result[key] = value
    return result


def _validate_arguments(arguments: JsonObject, schema: JsonObject) -> None:
    try:
        Draft202012Validator(cast(dict[str, object], schema)).validate(arguments)
    except ValidationError as error:
        raise McpGatewayInvocationInvalid(error.message) from error


def _validated_registration(
    registration: McpGatewayToolRegistration,
) -> McpGatewayToolRegistration:
    required_text = {
        "tool name": registration.tool_name,
        "description": registration.description,
        "target instance key": registration.target_instance_key,
        "component contract ID": registration.component_contract_id,
        "action ID": registration.action_id,
        "codec ID": registration.codec_id,
    }
    missing = [
        name
        for name, value in required_text.items()
        if not isinstance(value, str) or not value.strip()
    ]
    if missing:
        raise McpGatewayRegistrationInvalid(f"registration requires non-empty {missing[0]}")
    if any(
        not isinstance(version, int) or isinstance(version, bool) or version < 1
        for version in (registration.schema_version, registration.codec_version)
    ):
        raise McpGatewayRegistrationInvalid("schema and codec versions must be positive integers")
    if not registration.component_contract_id.startswith(("component.", "application.")):
        raise McpGatewayRegistrationInvalid("target contract must have a stable ID")

    parameter_schema = _copy_json_object(
        registration.parameter_schema, field_name="parameter schema"
    )
    if parameter_schema.get("type") != "object":
        raise McpGatewayRegistrationInvalid("v1 tool parameter schema must describe an object")
    try:
        Draft202012Validator.check_schema(cast(dict[str, object], parameter_schema))
    except SchemaError as error:
        raise McpGatewayRegistrationInvalid(
            f"invalid v1 tool parameter schema: {error.message}"
        ) from error
    annotations = _copy_json_object(registration.annotations, field_name="annotations")
    title = annotations.get("title")
    if title is not None and not isinstance(title, str):
        raise McpGatewayRegistrationInvalid("annotation title must be a string or null")
    for hint in (
        "readOnlyHint",
        "destructiveHint",
        "idempotentHint",
        "openWorldHint",
    ):
        value = annotations.get(hint)
        if value is not None and not isinstance(value, bool):
            raise McpGatewayRegistrationInvalid(
                f"annotation {hint} must be a boolean or null"
            )
    return replace(
        registration,
        parameter_schema=parameter_schema,
        annotations=annotations,
    )


def _copy_registration(registration: McpGatewayToolRegistration) -> McpGatewayToolRegistration:
    return replace(
        registration,
        parameter_schema=deepcopy(registration.parameter_schema),
        annotations=deepcopy(registration.annotations),
    )


def _copy_json_object(value: object, *, field_name: str) -> JsonObject:
    if not isinstance(value, dict) or not _is_json_value(value):
        raise McpGatewayRegistrationInvalid(f"registration {field_name} must be a JSON object")
    return cast(JsonObject, deepcopy(value))


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | bool | int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item) for key, item in value.items()
        )
    return False
