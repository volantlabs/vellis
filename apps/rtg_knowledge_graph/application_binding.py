from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast

from components.runtime.message_runtime import (
    JsonObject,
    RuntimeReplayMode,
    RuntimeTraceDisposition,
)
from components.runtime.messaging import (
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeArgumentDescriptor,
    RuntimeConsistencyAccess,
    RuntimeFailureBindingDescriptor,
    RuntimePayloadDisposition,
)


def load_application_binding(
    component_contract_id: str,
) -> dict[str, RuntimeActionBindingDescriptor]:
    manifest = json.loads(
        files("apps.rtg_knowledge_graph.resources")
        .joinpath("model_app_manifest.json")
        .read_text(encoding="utf-8")
    )
    if not isinstance(manifest, dict):
        raise RuntimeError("generated application manifest is invalid")
    if component_contract_id == "application.vellis.facade":
        values = manifest.get("tools")
        if not isinstance(values, list):
            raise RuntimeError("generated application manifest lacks facade bindings")
        actions = [cast(dict[str, Any], value) for value in values if isinstance(value, dict)]
    else:
        bindings = manifest.get("application_bindings")
        if not isinstance(bindings, list):
            raise RuntimeError("generated application manifest lacks application bindings")
        match = next(
            (
                value
                for value in bindings
                if isinstance(value, dict)
                and value.get("component_contract_id") == component_contract_id
            ),
            None,
        )
        if not isinstance(match, dict) or not isinstance(match.get("actions"), list):
            raise RuntimeError(
                f"generated application binding is unavailable: {component_contract_id}"
            )
        actions = [
            cast(dict[str, Any], value)
            for value in match["actions"]
            if isinstance(value, dict)
        ]
    descriptors: dict[str, RuntimeActionBindingDescriptor] = {}
    for value in actions:
        name = str(value.get("method_name", value.get("name", "")))
        if not name or name in descriptors:
            raise RuntimeError(f"invalid application action registration: {name!r}")
        failure_names = tuple(str(item) for item in cast(list[object], value["failure_names"]))
        failure_codec = str(value["failure_codec_id"])
        schema_version = value.get("schema_version", value.get("message_schema_version"))
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise RuntimeError(f"application action {name} has no schema version")
        descriptors[name] = RuntimeActionBindingDescriptor(
            component_contract_id=component_contract_id,
            action_id=str(value.get("action_id", value.get("target_action_id"))),
            binding_id=str(value["binding_id"]),
            binding_version=int(value["binding_version"]),
            schema_version=schema_version,
            request_codec_id=str(value["request_codec_id"]),
            result_codec_id=str(value["result_codec_id"]),
            failure_codec_id=failure_codec,
            idempotency=RuntimeActionIdempotency(str(value["idempotency"])),
            replay_mode=RuntimeReplayMode(str(value["replay_mode"])),
            concurrency_lane=str(value["concurrency_lane"]),
            consistency_group=cast(str | None, value.get("consistency_group")),
            consistency_access=RuntimeConsistencyAccess(str(value["consistency_access"])),
            deadline_seconds=float(value["deadline_seconds"]),
            externally_effectful=bool(value.get("externally_effectful", False)),
            request_codec_version=int(value["request_codec_version"]),
            result_codec_version=int(value["result_codec_version"]),
            failure_codec_version=int(value["failure_codec_version"]),
            request_arguments=tuple(
                RuntimeArgumentDescriptor(
                    name=str(item["name"]),
                    required=bool(item["required"]),
                    default=item.get("default"),
                    schema=cast(JsonObject, item["schema"]),
                )
                for item in cast(list[dict[str, object]], value["request_arguments"])
            ),
            supported_failure_names=failure_names,
            failure_bindings=tuple(
                RuntimeFailureBindingDescriptor(
                    failure_name=item,
                    codec_id=failure_codec,
                    codec_version=int(value["failure_codec_version"]),
                    content_type="application/json",
                    trace_disposition=RuntimeTraceDisposition.ABORTED,
                )
                for item in failure_names
            ),
            recovery_authorized=bool(value["recovery_authorized"]),
            request_payload_disposition=RuntimePayloadDisposition(
                str(value["request_payload_disposition"])
            ),
            result_payload_disposition=RuntimePayloadDisposition(
                str(value["result_payload_disposition"])
            ),
            fault_payload_disposition=RuntimePayloadDisposition(
                str(value["fault_payload_disposition"])
            ),
            effect_payload_disposition=(
                RuntimePayloadDisposition(str(value["effect_payload_disposition"]))
                if value.get("effect_payload_disposition") is not None
                else None
            ),
            request_schema=cast(JsonObject, value["request_schema"]),
            result_schema=cast(JsonObject, value["result_schema"]),
            fault_schema=cast(JsonObject, value["fault_schema"]),
        )
    return descriptors
