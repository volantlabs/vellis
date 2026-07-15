from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast

from components.interface.mcp_gateway import McpGatewayToolRegistration
from components.runtime.message_runtime import (
    ComponentOccurrenceDeclaration,
    JsonObject,
    RuntimeCuratedOperationDeclaration,
    RuntimeReplayMode,
    RuntimeTopologyManifest,
)


def model_mcp_gateway_registrations() -> tuple[McpGatewayToolRegistration, ...]:
    """Load the generated, curated Vellis MCP-to-message registration inventory."""
    manifest = model_application_manifest()
    tools = manifest.get("tools")
    if not isinstance(tools, list):
        raise RuntimeError("model application manifest has no tool registrations")
    registrations: list[McpGatewayToolRegistration] = []
    for value in tools:
        if not isinstance(value, dict):
            raise RuntimeError("model application manifest contains an invalid tool registration")
        registrations.append(_registration(cast(dict[str, Any], value)))
    return tuple(registrations)


def model_application_manifest() -> dict[str, Any]:
    """Load the generated static application composition manifest."""
    resource = files("apps.rtg_knowledge_graph.resources").joinpath("model_app_manifest.json")
    manifest = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("model application manifest is not an object")
    return cast(dict[str, Any], manifest)


def model_runtime_topology_manifest() -> RuntimeTopologyManifest:
    """Decode the complete generated runtime topology contract."""
    manifest = model_application_manifest()
    runtime = manifest.get("runtime")
    occurrences = manifest.get("occurrences")
    tools = manifest.get("tools")
    if (
        not isinstance(runtime, dict)
        or not isinstance(occurrences, list)
        or not isinstance(tools, list)
    ):
        raise RuntimeError("generated application manifest lacks runtime topology")
    runtime_key = runtime.get("runtime_key")
    schema_version = manifest.get("schema_version")
    manifest_hash = manifest.get("manifest_hash")
    if (
        not isinstance(runtime_key, str)
        or not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or not isinstance(manifest_hash, str)
    ):
        raise RuntimeError("generated application manifest has invalid runtime identity")
    return RuntimeTopologyManifest(
        runtime_key=runtime_key,
        manifest_schema_version=schema_version,
        occurrences=tuple(_occurrence_declaration(value) for value in occurrences),
        curated_operations=tuple(_operation_declaration(value) for value in tools),
        manifest_hash=manifest_hash,
    )


def _registration(value: dict[str, Any]) -> McpGatewayToolRegistration:
    def required_string(name: str) -> str:
        item = value.get(name)
        if not isinstance(item, str) or not item:
            raise RuntimeError(f"tool registration lacks {name}")
        return item

    parameter_schema = value.get("parameter_schema")
    annotations = value.get("annotations")
    if not isinstance(parameter_schema, dict) or not isinstance(annotations, dict):
        raise RuntimeError("tool registration lacks parameter schema or annotations")
    return McpGatewayToolRegistration(
        tool_name=required_string("name"),
        description=required_string("description"),
        parameter_schema=cast(JsonObject, parameter_schema),
        annotations=cast(JsonObject, annotations),
        target_instance_key=required_string("target_instance_key"),
        component_contract_id=required_string("target_component_contract_id"),
        action_id=required_string("target_action_id"),
        schema_version=_positive_integer(value, "message_schema_version"),
        codec_id=required_string("codec_id"),
        codec_version=_positive_integer(value, "codec_version"),
    )


def _positive_integer(value: dict[str, Any], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool) or item < 1:
        raise RuntimeError(f"tool registration lacks positive {name}")
    return item


def _occurrence_declaration(value: object) -> ComponentOccurrenceDeclaration:
    if not isinstance(value, dict):
        raise RuntimeError("runtime occurrence declaration is not an object")

    def required_string(name: str) -> str:
        item = value.get(name)
        if not isinstance(item, str) or not item:
            raise RuntimeError(f"runtime occurrence lacks {name}")
        return item

    configuration = value.get("configuration_references")
    if configuration is None:
        single = value.get("configuration_reference")
        configuration = [] if single is None else [single]
    if not isinstance(configuration, list) or any(
        not isinstance(reference, str) for reference in configuration
    ):
        raise RuntimeError("runtime occurrence configuration references are invalid")
    replay_authority = required_string("replay_authority")
    try:
        replay_mode = RuntimeReplayMode(replay_authority)
    except ValueError as error:
        raise RuntimeError(
            f"runtime occurrence has invalid replay authority {replay_authority!r}"
        ) from error
    return ComponentOccurrenceDeclaration(
        instance_key=required_string("instance_key"),
        component_contract_id=required_string("component_contract_id"),
        binding_id=required_string("runtime_binding_id"),
        binding_version=_positive_integer(value, "binding_version"),
        queue_capacity=_optional_positive_integer(value, "queue_capacity", 128),
        max_in_flight=_optional_positive_integer(value, "max_in_flight", 1),
        replay_authority=replay_mode,
        configuration_references=tuple(configuration),
    )


def _operation_declaration(value: object) -> RuntimeCuratedOperationDeclaration:
    if not isinstance(value, dict):
        raise RuntimeError("curated operation declaration is not an object")

    def required_string(name: str) -> str:
        item = value.get(name)
        if not isinstance(item, str) or not item:
            raise RuntimeError(f"curated operation lacks {name}")
        return item

    return RuntimeCuratedOperationDeclaration(
        operation_id=required_string("operation_id"),
        target_instance_key=required_string("target_instance_key"),
        component_contract_id=required_string("target_component_contract_id"),
        action_id=required_string("target_action_id"),
        schema_version=_positive_integer(value, "message_schema_version"),
    )


def _optional_positive_integer(value: dict[str, Any], name: str, default: int) -> int:
    item = value.get(name, default)
    if not isinstance(item, int) or isinstance(item, bool) or item < 1:
        raise RuntimeError(f"runtime occurrence has invalid {name}")
    return item
