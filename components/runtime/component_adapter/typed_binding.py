from __future__ import annotations

import inspect
import json
import os
import types
import typing
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from dataclasses import field as dataclass_field
from datetime import datetime
from enum import Enum
from importlib.resources import files
from types import NoneType
from typing import Any, cast, get_args, get_origin, get_type_hints, overload
from uuid import UUID

from components.runtime.component_adapter.native import (
    ActionBinding,
    ComponentAdapter,
    ComponentExecution,
    ReplayStateBinding,
    encode_json,
)
from components.runtime.component_adapter.protocol import (
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeArgumentDescriptor,
    RuntimeBindingInvalid,
    RuntimeFailureBindingDescriptor,
)
from components.runtime.message_runtime.protocol import (
    JsonObject,
    JsonValue,
    RuntimeReplayMode,
    RuntimeTraceDisposition,
)
from components.runtime.messaging import (
    ActionRef,
    RuntimeConsistencyAccess,
    RuntimePayloadDisposition,
)


@dataclass(frozen=True, slots=True)
class RuntimeBindingAction:
    action_id: str
    method_name: str
    replay_mode: RuntimeReplayMode
    idempotency: RuntimeActionIdempotency
    resolved_argument_from_result: str | None = None
    externally_effectful: bool = False
    concurrency_lane: str = "serialized"
    consistency_group: str | None = None
    consistency_access: RuntimeConsistencyAccess = RuntimeConsistencyAccess.INDEPENDENT
    deadline_seconds: float | None = None
    modeled_fault_trace_disposition: RuntimeTraceDisposition = RuntimeTraceDisposition.ABORTED
    replay_effect_builder: (
        Callable[[tuple[object, ...], dict[str, object], object], JsonObject] | None
    ) = None
    failure_replay_effect_builder: Callable[[object, Exception], JsonObject] | None = None
    failure_replay_effect_applier: Callable[[object, JsonObject], object] | None = None
    failure_types: tuple[type[Exception], ...] | None = None
    failure_trace_dispositions: tuple[tuple[type[Exception], RuntimeTraceDisposition], ...] = ()
    failure_replay_effect_types: tuple[type[Exception], ...] | None = None
    recovery_authorized: bool = False
    request_payload_disposition: RuntimePayloadDisposition = RuntimePayloadDisposition.COMMAND
    result_payload_disposition: RuntimePayloadDisposition = (
        RuntimePayloadDisposition.QUERY_RESULT
    )
    fault_payload_disposition: RuntimePayloadDisposition = RuntimePayloadDisposition.DIAGNOSTIC
    effect_payload_disposition: RuntimePayloadDisposition | None = None
    request_codec_id: str = ""
    request_codec_version: int = 1
    result_codec_id: str = ""
    result_codec_version: int = 1
    failure_codec_id: str = ""
    failure_codec_version: int = 1
    schema_version: int = 1
    request_arguments: tuple[RuntimeArgumentDescriptor, ...] = ()
    request_schema: JsonObject = dataclass_field(default_factory=dict)
    result_schema: JsonObject = dataclass_field(default_factory=dict)
    fault_schema: JsonObject = dataclass_field(default_factory=dict)
    canonical_effect_schema_version: int | None = None
    canonical_effect_codec_id: str | None = None
    canonical_effect_codec_version: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeBindingResource:
    component_contract_id: str
    binding_id: str
    binding_version: int
    actions: tuple[RuntimeBindingAction, ...]


def load_runtime_binding_resource(
    package: str | None,
    *,
    failure_types: Mapping[str, tuple[type[Exception], ...]],
) -> RuntimeBindingResource:
    """Load model-projected metadata and bind its failure names to Python codecs."""

    if package is None:
        raise RuntimeBindingInvalid("runtime binding resource requires a package")
    resource = files(package).joinpath("resources/runtime_binding.json")
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise RuntimeBindingInvalid(f"invalid runtime binding resource: {resource}")
    contract = raw.get("component_contract_id")
    binding_id = raw.get("binding_id")
    binding_version = raw.get("binding_version")
    action_values = raw.get("actions")
    if (
        not isinstance(contract, str)
        or not isinstance(binding_id, str)
        or not isinstance(binding_version, int)
        or not isinstance(action_values, list)
    ):
        raise RuntimeBindingInvalid(f"incomplete runtime binding resource: {resource}")
    actions: list[RuntimeBindingAction] = []
    seen: set[str] = set()
    for value in action_values:
        if not isinstance(value, dict) or not isinstance(value.get("method_name"), str):
            raise RuntimeBindingInvalid(f"invalid action in runtime binding resource: {resource}")
        method_name = str(value["method_name"])
        if method_name in seen:
            raise RuntimeBindingInvalid(f"duplicate runtime action registration: {method_name}")
        seen.add(method_name)
        action_id = value.get("action_id")
        if action_id != f"{contract}.{method_name}":
            raise RuntimeBindingInvalid(f"runtime action identity differs: {method_name}")
        mapped_failures = failure_types.get(method_name)
        if mapped_failures is None:
            raise RuntimeBindingInvalid(
                f"runtime action has no Python failure mapping: {method_name}"
            )
        declared_failure_names = value.get("failure_names")
        if declared_failure_names != [failure.__name__ for failure in mapped_failures]:
            raise RuntimeBindingInvalid(f"runtime failure mapping differs: {method_name}")
        disposition_values = value.get("failure_dispositions", {})
        if not isinstance(disposition_values, dict):
            raise RuntimeBindingInvalid(f"invalid failure dispositions: {method_name}")
        failures_by_name = {failure.__name__: failure for failure in mapped_failures}
        unknown_dispositions = set(disposition_values) - set(failures_by_name)
        if unknown_dispositions:
            raise RuntimeBindingInvalid(
                f"unknown failure disposition for {method_name}: {sorted(unknown_dispositions)}"
            )
        raw_arguments = value.get("request_arguments")
        request_schema = value.get("request_schema")
        result_schema = value.get("result_schema")
        fault_schema = value.get("fault_schema")
        if (
            not isinstance(raw_arguments, list)
            or not isinstance(request_schema, dict)
            or not isinstance(result_schema, dict)
            or not isinstance(fault_schema, dict)
        ):
            raise RuntimeBindingInvalid(f"runtime action schemas are incomplete: {method_name}")
        request_arguments = tuple(
            RuntimeArgumentDescriptor(
                name=str(argument["name"]),
                required=bool(argument["required"]),
                default=argument.get("default"),
                schema=cast(JsonObject, argument["schema"]),
            )
            for argument in raw_arguments
            if isinstance(argument, dict) and isinstance(argument.get("schema"), dict)
        )
        if len(request_arguments) != len(raw_arguments):
            raise RuntimeBindingInvalid(f"runtime arguments are malformed: {method_name}")
        actions.append(
            RuntimeBindingAction(
                action_id=str(action_id),
                method_name=method_name,
                replay_mode=RuntimeReplayMode(str(value["replay_mode"])),
                idempotency=RuntimeActionIdempotency(str(value["idempotency"])),
                resolved_argument_from_result=cast(
                    str | None, value.get("resolved_argument_from_result")
                ),
                externally_effectful=bool(value.get("externally_effectful", False)),
                concurrency_lane=str(value.get("concurrency_lane", "serialized")),
                consistency_group=cast(str | None, value.get("consistency_group")),
                consistency_access=RuntimeConsistencyAccess(
                    str(value.get("consistency_access", "independent"))
                ),
                deadline_seconds=cast(float | None, value.get("deadline_seconds")),
                modeled_fault_trace_disposition=RuntimeTraceDisposition(
                    str(value.get("modeled_fault_trace_disposition", "aborted"))
                ),
                failure_types=mapped_failures,
                failure_trace_dispositions=tuple(
                    (failures_by_name[name], RuntimeTraceDisposition(str(disposition)))
                    for name, disposition in disposition_values.items()
                ),
                recovery_authorized=bool(value.get("recovery_authorized", False)),
                request_payload_disposition=RuntimePayloadDisposition(
                    str(value.get("request_payload_disposition", "command"))
                ),
                result_payload_disposition=RuntimePayloadDisposition(
                    str(value.get("result_payload_disposition", "query_result"))
                ),
                fault_payload_disposition=RuntimePayloadDisposition(
                    str(value.get("fault_payload_disposition", "diagnostic"))
                ),
                effect_payload_disposition=(
                    RuntimePayloadDisposition(str(value["effect_payload_disposition"]))
                    if value.get("effect_payload_disposition") is not None
                    else None
                ),
                request_codec_id=str(value["request_codec_id"]),
                request_codec_version=int(value["request_codec_version"]),
                result_codec_id=str(value["result_codec_id"]),
                result_codec_version=int(value["result_codec_version"]),
                failure_codec_id=str(value["failure_codec_id"]),
                failure_codec_version=int(value["failure_codec_version"]),
                schema_version=int(value["schema_version"]),
                request_arguments=request_arguments,
                request_schema=cast(JsonObject, request_schema),
                result_schema=cast(JsonObject, result_schema),
                fault_schema=cast(JsonObject, fault_schema),
                canonical_effect_schema_version=cast(
                    int | None, value.get("canonical_effect_schema_version")
                ),
                canonical_effect_codec_id=cast(
                    str | None, value.get("canonical_effect_codec_id")
                ),
                canonical_effect_codec_version=cast(
                    int | None, value.get("canonical_effect_codec_version")
                ),
            )
        )
    if set(failure_types) != seen:
        raise RuntimeBindingInvalid(
            f"Python failure registrations invent actions: {sorted(set(failure_types) - seen)}"
        )
    return RuntimeBindingResource(contract, binding_id, binding_version, tuple(actions))


def runtime_binding_descriptor(
    binding: RuntimeBindingResource,
    method_name: str,
) -> RuntimeActionBindingDescriptor:
    """Materialize one descriptor from model-projected metadata and explicit codecs."""

    matches = [action for action in binding.actions if action.method_name == method_name]
    if len(matches) != 1:
        raise RuntimeBindingInvalid(f"runtime binding action is unavailable: {method_name}")
    action = matches[0]
    request_codec = action.request_codec_id
    result_codec = action.result_codec_id
    failure_codec = action.failure_codec_id
    dispositions = dict(action.failure_trace_dispositions)
    has_effect = action.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
    return RuntimeActionBindingDescriptor(
        component_contract_id=binding.component_contract_id,
        action_id=action.action_id,
        binding_id=binding.binding_id,
        binding_version=binding.binding_version,
        schema_version=action.schema_version,
        request_codec_id=request_codec,
        result_codec_id=result_codec,
        failure_codec_id=failure_codec,
        idempotency=action.idempotency,
        replay_mode=action.replay_mode,
        concurrency_lane=action.concurrency_lane,
        consistency_group=action.consistency_group,
        consistency_access=action.consistency_access,
        deadline_seconds=action.deadline_seconds,
        externally_effectful=action.externally_effectful,
        request_codec_version=action.request_codec_version,
        result_codec_version=action.result_codec_version,
        failure_codec_version=action.failure_codec_version,
        request_arguments=action.request_arguments,
        supported_failure_names=tuple(failure.__name__ for failure in action.failure_types or ()),
        failure_bindings=tuple(
            RuntimeFailureBindingDescriptor(
                failure_name=failure.__name__,
                codec_id=failure_codec,
                codec_version=action.failure_codec_version,
                content_type="application/json",
                trace_disposition=dispositions.get(failure, action.modeled_fault_trace_disposition),
            )
            for failure in action.failure_types or ()
        ),
        canonical_effect_schema_version=(
            action.canonical_effect_schema_version if has_effect else None
        ),
        canonical_effect_codec_id=action.canonical_effect_codec_id if has_effect else None,
        canonical_effect_codec_version=(
            action.canonical_effect_codec_version if has_effect else None
        ),
        modeled_fault_trace_disposition=action.modeled_fault_trace_disposition,
        recovery_authorized=action.recovery_authorized,
        request_payload_disposition=action.request_payload_disposition,
        result_payload_disposition=action.result_payload_disposition,
        fault_payload_disposition=action.fault_payload_disposition,
        effect_payload_disposition=action.effect_payload_disposition,
        request_schema=action.request_schema,
        result_schema=action.result_schema,
        fault_schema=action.fault_schema,
    )


def create_typed_component_adapter(
    component: object,
    protocol_type: type[object],
    *,
    binding: RuntimeBindingResource,
    failure_types: tuple[type[Exception], ...],
    replay_state: ReplayStateBinding | None = None,
):
    """Build an adapter from an explicit method inventory and protocol annotations."""
    return _create_typed_adapter(
        component,
        protocol_type,
        binding=binding,
        failure_types=failure_types,
        replay_state=replay_state,
        handlers=None,
    )


def create_typed_handler_adapter(
    protocol_type: type[object],
    *,
    binding: RuntimeBindingResource,
    failure_types: tuple[type[Exception], ...],
    handlers: Mapping[
        str,
        Callable[
            [tuple[object, ...], dict[str, object], ComponentExecution],
            Awaitable[None],
        ],
    ],
    replay_state: ReplayStateBinding | None = None,
) -> ComponentAdapter:
    """Build ordinary typed action registrations around explicit async handlers."""
    return _create_typed_adapter(
        None,
        protocol_type,
        binding=binding,
        failure_types=failure_types,
        replay_state=replay_state,
        handlers=handlers,
    )


def _create_typed_adapter(
    component: object | None,
    protocol_type: type[object],
    *,
    binding: RuntimeBindingResource,
    failure_types: tuple[type[Exception], ...],
    replay_state: ReplayStateBinding | None,
    handlers: Mapping[
        str,
        Callable[
            [tuple[object, ...], dict[str, object], ComponentExecution],
            Awaitable[None],
        ],
    ]
    | None,
) -> ComponentAdapter:

    binding_id = binding.binding_id
    bindings: list[ActionBinding] = []
    for spec in binding.actions:
        action_failure_types = (
            spec.failure_types if spec.failure_types is not None else failure_types
        )
        failure_dispositions = dict(spec.failure_trace_dispositions)
        if len(failure_dispositions) != len(spec.failure_trace_dispositions):
            raise RuntimeBindingInvalid(
                f"duplicate failure disposition override for {spec.method_name}"
            )
        if any(failure not in action_failure_types for failure in failure_dispositions):
            raise RuntimeBindingInvalid(
                f"failure disposition override is not a supported failure for {spec.method_name}"
            )
        failure_replay_effect_types = (
            action_failure_types
            if spec.failure_replay_effect_types is None
            else spec.failure_replay_effect_types
        )
        if any(failure not in action_failure_types for failure in failure_replay_effect_types):
            raise RuntimeBindingInvalid(
                f"failure replay effect is not a supported failure for {spec.method_name}"
            )
        if spec.failure_replay_effect_builder is None and spec.failure_replay_effect_types:
            raise RuntimeBindingInvalid(
                f"failure replay effect types require an effect builder for {spec.method_name}"
            )
        if (
            spec.replay_effect_builder is not None
            and spec.replay_mode is not RuntimeReplayMode.CANONICAL_EFFECT
        ):
            raise RuntimeBindingInvalid(
                "custom success replay effects require canonical-effect replay mode"
            )
        if (spec.failure_replay_effect_builder is None) != (
            spec.failure_replay_effect_applier is None
        ):
            raise RuntimeBindingInvalid(
                "modeled-fault replay requires both an effect builder and applier"
            )
        if (
            spec.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
            and spec.failure_replay_effect_builder is not None
        ):
            raise RuntimeBindingInvalid(
                "typed canonical actions cannot also declare a distinct modeled-fault effect"
            )
        protocol_method = inspect.getattr_static(protocol_type, spec.method_name, None)
        if protocol_method is None:
            raise RuntimeBindingInvalid(
                f"protocol has no explicitly bound method: {spec.method_name}"
            )
        handler = handlers.get(spec.method_name) if handlers is not None else None
        method = getattr(component, spec.method_name, None) if component is not None else None
        if handler is None and not callable(method):
            raise RuntimeBindingInvalid(
                f"component does not implement explicitly bound method: {spec.method_name}"
            )
        signature = inspect.signature(protocol_method)
        hints = get_type_hints(protocol_method)
        descriptor = runtime_binding_descriptor(binding, spec.method_name)
        projected_names = tuple(item.name for item in descriptor.request_arguments)
        python_names = tuple(
            name for name in signature.parameters if name not in {"self", "cls"}
        )
        if projected_names != python_names:
            raise RuntimeBindingInvalid(
                f"modeled arguments differ for {spec.method_name}: "
                f"{projected_names} != {python_names}"
            )
        if spec.failure_replay_effect_builder is not None:
            descriptor = replace(
                descriptor,
                canonical_effect_schema_version=descriptor.canonical_effect_schema_version or 1,
                canonical_effect_codec_id=(
                    descriptor.canonical_effect_codec_id
                    or f"{binding_id}.{descriptor.action_id}.effect.json"
                ),
                canonical_effect_codec_version=descriptor.canonical_effect_codec_version or 1,
                failure_bindings=tuple(
                    replace(
                        failure,
                        replay_mode=(
                            RuntimeReplayMode.CANONICAL_EFFECT
                            if next(
                                item
                                for item in action_failure_types
                                if item.__name__ == failure.failure_name
                            )
                            in failure_replay_effect_types
                            else RuntimeReplayMode.NO_STATE_EFFECT
                        ),
                    )
                    for failure in descriptor.failure_bindings
                ),
            )

        def invoke(
            *args: object,
            method_name: str = spec.method_name,
            **kwargs: object,
        ) -> object:
            if component is None:
                raise RuntimeBindingInvalid(f"typed handler has no direct component: {method_name}")
            current_method = getattr(component, method_name, None)
            if not callable(current_method):
                raise RuntimeBindingInvalid(
                    f"component no longer implements bound method: {method_name}"
                )
            return current_method(*args, **kwargs)

        def decode_request(
            payload: JsonObject,
            *,
            signature: inspect.Signature = signature,
            hints: dict[str, object] = hints,
        ) -> tuple[tuple[object, ...], dict[str, object]]:
            unknown = set(payload) - {
                name for name in signature.parameters if name not in {"self", "cls"}
            }
            if unknown:
                raise ValueError(f"unknown arguments: {sorted(unknown)}")
            decoded: dict[str, object] = {}
            for name, parameter in signature.parameters.items():
                if name in {"self", "cls"}:
                    continue
                if name not in payload:
                    if parameter.default is inspect.Parameter.empty:
                        raise ValueError(f"missing required argument: {name}")
                    continue
                decoded[name] = decode_typed(payload[name], hints.get(name, object))
            return (), decoded

        def build_effect(
            _args: tuple[object, ...],
            kwargs: dict[str, object],
            result: object,
            *,
            resolved_name: str | None = spec.resolved_argument_from_result,
            custom_builder: (
                Callable[[tuple[object, ...], dict[str, object], object], JsonObject] | None
            ) = spec.replay_effect_builder,
        ) -> JsonObject:
            if custom_builder is not None:
                return custom_builder(_args, kwargs, result)
            arguments = dict(kwargs)
            if resolved_name is not None:
                arguments[resolved_name] = result
            return {"arguments": cast(JsonValue, encode_json(arguments))}

        def apply_effect(
            payload: JsonObject,
            *,
            method_name: str = spec.method_name,
            signature: inspect.Signature = signature,
            hints: dict[str, object] = hints,
        ) -> object:
            if component is None:
                raise RuntimeBindingInvalid(
                    f"typed handler has no direct replay component: {method_name}"
                )
            arguments = payload.get("arguments")
            if not isinstance(arguments, dict):
                raise ValueError("canonical effect arguments must be an object")
            _, decoded = _decode_arguments(cast(JsonObject, arguments), signature, hints)
            current_method = getattr(component, method_name, None)
            if not callable(current_method):
                raise RuntimeBindingInvalid(
                    f"component no longer implements bound method: {method_name}"
                )
            return current_method(**decoded)

        def build_failure_effect(
            error: Exception,
            *,
            builder: Callable[[object, Exception], JsonObject] | None = (
                spec.failure_replay_effect_builder
            ),
        ) -> JsonObject:
            if builder is None:
                raise RuntimeBindingInvalid("modeled-fault replay builder is not configured")
            if component is None:
                raise RuntimeBindingInvalid("typed handler has no failure-effect component")
            return builder(component, error)

        def apply_failure_effect(
            payload: JsonObject,
            *,
            applier: Callable[[object, JsonObject], object] | None = (
                spec.failure_replay_effect_applier
            ),
        ) -> object:
            if applier is None:
                raise RuntimeBindingInvalid("modeled-fault replay applier is not configured")
            if component is None:
                raise RuntimeBindingInvalid("typed handler has no failure-effect component")
            return applier(component, payload)

        bindings.append(
            ActionBinding(
                descriptor=descriptor,
                invoke=invoke if handler is None else None,
                handler=handler,
                decode_request=decode_request,
                encode_result=encode_json,
                failure_types=action_failure_types,
                build_replay_effect=(
                    build_effect if spec.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT else None
                ),
                apply_replay_effect=(
                    apply_effect
                    if spec.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
                    else (
                        apply_failure_effect
                        if spec.failure_replay_effect_applier is not None
                        else None
                    )
                ),
                build_failure_replay_effect=(
                    build_failure_effect if spec.failure_replay_effect_builder is not None else None
                ),
            )
        )
    return ComponentAdapter(tuple(bindings), replay_state=replay_state)


def create_action_catalog(
    binding: RuntimeBindingResource,
) -> dict[str, ActionRef]:
    """Create the message-oriented action references shared by callers and handlers."""
    component_contract_id = binding.component_contract_id
    request_codec = f"codec.python.{component_contract_id}.request.json"
    return {
        spec.method_name: ActionRef(
            component_contract_id=component_contract_id,
            action_id=f"{component_contract_id}.{spec.method_name}",
            schema_version=1,
            request_codec_id=request_codec,
        )
        for spec in binding.actions
    }


@overload
def decode_typed[T](value: object, annotation: type[T]) -> T: ...


@overload
def decode_typed(value: object, annotation: object) -> Any: ...


def decode_typed(value: object, annotation: object) -> Any:
    if annotation in {Any, object, inspect.Signature.empty}:
        return value
    if getattr(annotation, "__name__", None) in {"JsonValue", "JsonObject", "JsonScalar"}:
        return value
    if type(annotation).__name__ == "TypeAliasType":
        return decode_typed(value, cast(Any, annotation).__value__)
    if annotation is None or annotation is NoneType:
        if value is not None:
            raise ValueError("expected null")
        return None
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in {typing.Union, types.UnionType}:
        errors: list[Exception] = []
        for alternative in arguments:
            try:
                return decode_typed(value, alternative)
            except (TypeError, ValueError, KeyError) as error:
                errors.append(error)
        raise ValueError(f"value does not match union {annotation}: {errors}")
    if origin is typing.Literal:
        if value not in arguments:
            raise ValueError(f"expected one of {arguments}")
        return value
    if origin is tuple:
        if not isinstance(value, list | tuple):
            raise ValueError("expected array")
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(decode_typed(item, arguments[0]) for item in value)
        if len(value) != len(arguments):
            raise ValueError("tuple length differs")
        return tuple(
            decode_typed(item, item_type) for item, item_type in zip(value, arguments, strict=True)
        )
    if origin is list:
        if not isinstance(value, list):
            raise ValueError("expected array")
        item_type = arguments[0] if arguments else object
        return [decode_typed(item, item_type) for item in value]
    if origin in {dict, Mapping}:
        if not isinstance(value, dict):
            raise ValueError("expected object")
        key_type, item_type = arguments or (str, object)
        return {
            decode_typed(key, key_type): decode_typed(item, item_type)
            for key, item in value.items()
        }
    if origin is os.PathLike:
        if not isinstance(value, str):
            raise ValueError("expected path string")
        return value
    if annotation is UUID:
        return value if isinstance(value, UUID) else UUID(str(value))
    if annotation is datetime:
        if not isinstance(value, str):
            raise ValueError("expected ISO datetime string")
        return datetime.fromisoformat(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict):
            raise ValueError(f"expected object for {annotation.__name__}")
        hints = get_type_hints(annotation)
        known = {field.name for field in fields(annotation)}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"unknown {annotation.__name__} fields: {sorted(unknown)}")
        decoded = {
            field.name: decode_typed(value[field.name], hints.get(field.name, object))
            for field in fields(annotation)
            if field.name in value
        }
        return annotation(**decoded)
    if annotation in {str, int, float, bool}:
        if not isinstance(value, cast(type[object], annotation)):
            raise ValueError(f"expected {cast(type[object], annotation).__name__}")
        return value
    return value


def _decode_arguments(
    payload: JsonObject,
    signature: inspect.Signature,
    hints: dict[str, object],
) -> tuple[tuple[object, ...], dict[str, object]]:
    decoded: dict[str, object] = {}
    for name, parameter in signature.parameters.items():
        if name in {"self", "cls"}:
            continue
        if name not in payload:
            if parameter.default is inspect.Parameter.empty:
                raise ValueError(f"missing canonical effect argument: {name}")
            continue
        decoded[name] = decode_typed(payload[name], hints.get(name, object))
    return (), decoded


def _exception_type_map(
    roots: tuple[type[Exception], ...],
) -> dict[str, type[Exception]]:
    result: dict[str, type[Exception]] = {}
    pending = list(roots)
    while pending:
        exception_type = pending.pop()
        result[exception_type.__name__] = exception_type
        pending.extend(cast(tuple[type[Exception], ...], exception_type.__subclasses__()))
    return result


def _decode_failure(failure_type: type[Exception], message: str, evidence: JsonObject) -> Exception:
    try:
        signature = inspect.signature(failure_type)
        hints = get_type_hints(failure_type.__init__)
        keyword_arguments = {
            name: decode_typed(evidence[name], hints.get(name, object))
            for name in evidence
            if name in signature.parameters
        }
        return failure_type(message, **keyword_arguments)
    except TypeError, ValueError:
        return failure_type(message)
