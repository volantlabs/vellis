from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from typing import cast
from uuid import uuid5

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
from components.runtime.component_adapter import (
    ActionRef,
    ComponentAdapter,
    ComponentEndpoint,
    load_runtime_binding_resource,
)
from components.runtime.message_runtime import JsonObject, JsonValue
from components.runtime.messaging import (
    RuntimeAddress,
    RuntimeMessageKind,
    RuntimePayloadDisposition,
)

_CONTRACT = "component.interface.mcp_gateway"
_REQUEST_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_RUNTIME_BINDING = load_runtime_binding_resource(__package__, failure_types={})


class RuntimeMcpGateway:
    """Curated external mapping hosted by the same adapter as any component."""

    def __init__(
        self,
        registrations: tuple[McpGatewayToolRegistration, ...] = (),
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._registrations: dict[str, McpGatewayToolRegistration] = {}
        self._sealed = False
        self._registration_digest: str | None = None
        if registrations:
            self.register_tools(registrations)

    @property
    def registrations(self) -> tuple[McpGatewayToolRegistration, ...]:
        return tuple(_copy_registration(item) for item in self._registrations.values())

    @property
    def timeout_seconds(self) -> float | None:
        return self._timeout_seconds

    def register_tools(self, registrations: tuple[McpGatewayToolRegistration, ...]) -> None:
        if self._sealed:
            raise McpGatewayRegistrationInvalid("gateway registrations are sealed")
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

    @property
    def registration_digest(self) -> str | None:
        return self._registration_digest

    def seal(self) -> str:
        if not self._registrations:
            raise McpGatewayRegistrationInvalid("cannot seal an empty gateway")
        self._registration_digest = mcp_gateway_registration_digest(self.registrations)
        self._sealed = True
        return self._registration_digest

    def create_adapter(self) -> ComponentAdapter:
        """Attach the gateway occurrence as the source and response participant.

        External ingress starts the registered facade action as the root runtime
        request.  The gateway therefore needs only the same response-capable
        adapter used by every other occurrence; translation is not an extra
        message hop or a privileged participant type.
        """
        return ComponentAdapter(
            binding_id=_RUNTIME_BINDING.binding_id,
            binding_version=_RUNTIME_BINDING.binding_version,
            component_contract_id=_RUNTIME_BINDING.component_contract_id,
        )


class McpGatewayEndpoint:
    """Typed MCP mapping over a generic occurrence endpoint."""

    def __init__(
        self,
        endpoint: ComponentEndpoint,
        resolve_address: Callable[[str], RuntimeAddress],
        gateway: RuntimeMcpGateway,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._resolve_address = resolve_address
        self._gateway = gateway
        self._timeout_seconds = timeout_seconds

    @property
    def registrations(self) -> tuple[McpGatewayToolRegistration, ...]:
        return self._gateway.registrations

    async def invoke_tool(self, invocation: McpGatewayInvocation) -> McpGatewayOutcome:
        registration = next(
            (
                item
                for item in self._gateway.registrations
                if item.tool_name == invocation.tool_name
            ),
            None,
        )
        if registration is None:
            raise McpGatewayToolUnknown(invocation.tool_name)
        arguments = deepcopy(invocation.arguments)
        runtime_options = arguments.pop("runtime_options", None)
        request_key = _request_key(runtime_options)
        _validate_arguments(arguments, _target_parameter_schema(registration.parameter_schema))
        outcome = await self._endpoint.request(
            ActionRef(
                registration.component_contract_id,
                registration.action_id,
                registration.schema_version,
                registration.request_codec_id,
                registration.request_codec_version,
            ),
            arguments,
            target=self._resolve_address(registration.target_instance_key),
            timeout_seconds=self._timeout_seconds,
            message_id=(
                uuid5(self._endpoint.source.instance_id, request_key)
                if request_key
                else None
            ),
            idempotency_key=request_key,
        )
        payload = outcome.response.payload.value
        if not isinstance(payload, dict):
            raise McpGatewayInvocationInvalid(str(payload))
        if outcome.response.kind is RuntimeMessageKind.FAULT:
            result = _external_fault_result(cast(JsonObject, payload))
        else:
            result_value = payload.get("result")
            result = (
                cast(JsonObject, result_value)
                if isinstance(result_value, dict)
                else {"value": cast(JsonValue, result_value)}
            )
        result["runtime"] = {
            "message_id": str(outcome.request.message_id),
            "trace_id": str(outcome.response.trace_id),
            "terminal_position": outcome.terminal_position,
            "trace_disposition": outcome.trace_disposition.value,
            "request_key": request_key,
        }
        return McpGatewayOutcome(
            tool_name=invocation.tool_name,
            result=result,
            message_id=outcome.request.message_id,
            trace_id=outcome.response.trace_id,
            terminal_position=outcome.terminal_position,
            trace_disposition=outcome.trace_disposition,
        )


def _request_key(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"request_key"}:
        raise McpGatewayInvocationInvalid(
            "runtime_options must contain exactly request_key"
        )
    request_key = value.get("request_key")
    if not isinstance(request_key, str) or _REQUEST_KEY.fullmatch(request_key) is None:
        raise McpGatewayInvocationInvalid(
            "runtime_options.request_key must be 1-128 safe identifier characters"
        )
    return request_key


def _target_parameter_schema(schema: JsonObject) -> JsonObject:
    target = deepcopy(schema)
    properties = target.get("properties")
    if isinstance(properties, dict):
        properties.pop("runtime_options", None)
    return cast(JsonObject, target)


def _external_fault_result(payload: JsonObject) -> JsonObject:
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


def mcp_gateway_registration_digest(
    registrations: tuple[McpGatewayToolRegistration, ...],
) -> str:
    canonical = json.dumps(
        [
            {
                "tool_name": item.tool_name,
                "target_instance_key": item.target_instance_key,
                "component_contract_id": item.component_contract_id,
                "action_id": item.action_id,
                "schema_version": item.schema_version,
                "binding_id": item.binding_id,
                "binding_version": item.binding_version,
                "request_codec_id": item.request_codec_id,
                "request_codec_version": item.request_codec_version,
                "request_payload_disposition": item.request_payload_disposition.value,
                "result_payload_disposition": item.result_payload_disposition.value,
                "fault_payload_disposition": item.fault_payload_disposition.value,
                "effect_payload_disposition": (
                    item.effect_payload_disposition.value
                    if item.effect_payload_disposition is not None
                    else None
                ),
                "parameter_schema": item.parameter_schema,
            }
            for item in registrations
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validated_registration(
    registration: McpGatewayToolRegistration,
) -> McpGatewayToolRegistration:
    required_text = {
        "tool name": registration.tool_name,
        "description": registration.description,
        "target instance key": registration.target_instance_key,
        "component contract ID": registration.component_contract_id,
        "action ID": registration.action_id,
        "binding ID": registration.binding_id,
        "request codec ID": registration.request_codec_id,
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
        for version in (
            registration.schema_version,
            registration.binding_version,
            registration.request_codec_version,
        )
    ):
        raise McpGatewayRegistrationInvalid(
            "schema, binding, and codec versions must be positive integers"
        )
    if not all(
        isinstance(value, RuntimePayloadDisposition)
        for value in (
            registration.request_payload_disposition,
            registration.result_payload_disposition,
            registration.fault_payload_disposition,
        )
    ) or (
        registration.effect_payload_disposition is not None
        and not isinstance(
            registration.effect_payload_disposition,
            RuntimePayloadDisposition,
        )
    ):
        raise McpGatewayRegistrationInvalid("payload dispositions must be modeled values")
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
            raise McpGatewayRegistrationInvalid(f"annotation {hint} must be a boolean or null")
    return replace(
        registration,
        parameter_schema=parameter_schema,
        annotations=annotations,
    )


def _copy_registration(
    registration: McpGatewayToolRegistration,
) -> McpGatewayToolRegistration:
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
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False
