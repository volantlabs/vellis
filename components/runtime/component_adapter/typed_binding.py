from __future__ import annotations

import inspect
import os
import types
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from types import NoneType
from typing import Any, cast, get_args, get_origin, get_type_hints
from uuid import UUID

from components.runtime.component_adapter.implementation import (
    ActionBinding,
    MutableAdapterHost,
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
    MessageRuntime,
    RuntimeAddress,
    RuntimeMessageKind,
    RuntimeReplayMode,
    RuntimeTraceDisposition,
)


@dataclass(frozen=True, slots=True)
class MethodBindingSpec:
    method_name: str
    replay_mode: RuntimeReplayMode
    idempotency: RuntimeActionIdempotency
    resolved_argument_from_result: str | None = None
    externally_effectful: bool = False
    concurrency_lane: str = "serialized"
    max_in_flight: int = 1
    modeled_fault_trace_disposition: RuntimeTraceDisposition = RuntimeTraceDisposition.ABORTED
    replay_effect_builder: (
        Callable[[tuple[object, ...], dict[str, object], object], JsonObject] | None
    ) = None
    failure_replay_effect_builder: Callable[[object, Exception], JsonObject] | None = None
    failure_replay_effect_applier: Callable[[object, JsonObject], object] | None = None
    failure_types: tuple[type[Exception], ...] | None = None
    failure_trace_dispositions: tuple[
        tuple[type[Exception], RuntimeTraceDisposition], ...
    ] = ()
    failure_replay_effect_types: tuple[type[Exception], ...] | None = None
    recovery_authorized: bool = False


def create_typed_component_adapter(
    component: object | MutableAdapterHost[object],
    protocol_type: type[object],
    *,
    component_contract_id: str,
    binding_id: str,
    specs: tuple[MethodBindingSpec, ...],
    failure_types: tuple[type[Exception], ...],
    replay_state: ReplayStateBinding | None = None,
):
    """Build an adapter from an explicit method inventory and protocol annotations."""
    from components.runtime.component_adapter.implementation import ExplicitComponentAdapter

    request_codec = f"codec.python.{component_contract_id}.request.json"
    result_codec = f"codec.python.{component_contract_id}.result.json"
    failure_codec = f"codec.python.{component_contract_id}.failure.json"
    host = component if isinstance(component, MutableAdapterHost) else MutableAdapterHost(component)
    bindings: list[ActionBinding] = []
    for spec in specs:
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
                f"failure disposition override is not a supported failure for "
                f"{spec.method_name}"
            )
        failure_replay_effect_types = (
            action_failure_types
            if spec.failure_replay_effect_types is None
            else spec.failure_replay_effect_types
        )
        if any(
            failure not in action_failure_types
            for failure in failure_replay_effect_types
        ):
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
        method = getattr(host.resolve(), spec.method_name, None)
        if not callable(method):
            raise RuntimeBindingInvalid(
                f"component does not implement explicitly bound method: {spec.method_name}"
            )
        signature = inspect.signature(protocol_method)
        hints = get_type_hints(protocol_method)
        action_id = f"{component_contract_id}.{spec.method_name}"
        descriptor = RuntimeActionBindingDescriptor(
            component_contract_id=component_contract_id,
            action_id=action_id,
            binding_id=binding_id,
            binding_version=1,
            schema_version=1,
            request_codec_id=request_codec,
            result_codec_id=result_codec,
            failure_codec_id=failure_codec,
            idempotency=spec.idempotency,
            replay_mode=spec.replay_mode,
            concurrency_lane=spec.concurrency_lane,
            externally_effectful=spec.externally_effectful,
            request_codec_version=1,
            result_codec_version=1,
            failure_codec_version=1,
            request_arguments=tuple(
                RuntimeArgumentDescriptor(
                    name=name,
                    required=parameter.default is inspect.Parameter.empty,
                    default=(
                        None
                        if parameter.default is inspect.Parameter.empty
                        else encode_json(parameter.default)
                    ),
                )
                for name, parameter in signature.parameters.items()
                if name not in {"self", "cls"}
            ),
            supported_failure_names=tuple(
                failure.__name__ for failure in action_failure_types
            ),
            failure_bindings=tuple(
                RuntimeFailureBindingDescriptor(
                    failure_name=failure.__name__,
                    codec_id=failure_codec,
                    codec_version=1,
                    content_type="application/json",
                    trace_disposition=failure_dispositions.get(
                        failure, spec.modeled_fault_trace_disposition
                    ),
                    replay_mode=(
                        RuntimeReplayMode.CANONICAL_EFFECT
                        if spec.failure_replay_effect_builder is not None
                        and failure in failure_replay_effect_types
                        else RuntimeReplayMode.NO_STATE_EFFECT
                    ),
                )
                for failure in action_failure_types
            ),
            canonical_effect_schema_version=(
                1
                if spec.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
                or spec.failure_replay_effect_builder is not None
                else None
            ),
            canonical_effect_codec_id=(
                f"{binding_id}.{action_id}.effect.json"
                if spec.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
                or spec.failure_replay_effect_builder is not None
                else None
            ),
            canonical_effect_codec_version=(
                1
                if spec.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
                or spec.failure_replay_effect_builder is not None
                else None
            ),
            modeled_fault_trace_disposition=spec.modeled_fault_trace_disposition,
            max_in_flight=spec.max_in_flight,
            recovery_authorized=spec.recovery_authorized,
        )

        def invoke(
            *args: object,
            method_name: str = spec.method_name,
            **kwargs: object,
        ) -> object:
            current_method = getattr(host.resolve(), method_name, None)
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
            arguments = payload.get("arguments")
            if not isinstance(arguments, dict):
                raise ValueError("canonical effect arguments must be an object")
            _, decoded = _decode_arguments(cast(JsonObject, arguments), signature, hints)
            current_method = getattr(host.resolve(), method_name, None)
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
            return builder(host.resolve(), error)

        def apply_failure_effect(
            payload: JsonObject,
            *,
            applier: Callable[[object, JsonObject], object] | None = (
                spec.failure_replay_effect_applier
            ),
        ) -> object:
            if applier is None:
                raise RuntimeBindingInvalid("modeled-fault replay applier is not configured")
            return applier(host.resolve(), payload)

        bindings.append(
            ActionBinding(
                descriptor=descriptor,
                invoke=invoke,
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
    return ExplicitComponentAdapter(tuple(bindings), replay_state=replay_state)


class TypedMessageProxy:
    """Sync proxy exposing only the explicitly supplied protocol method inventory."""

    def __init__(
        self,
        runtime: MessageRuntime,
        source: RuntimeAddress,
        target: RuntimeAddress,
        protocol_type: type[object],
        *,
        component_contract_id: str,
        specs: tuple[MethodBindingSpec, ...],
        failure_types: tuple[type[Exception], ...],
    ) -> None:
        from components.runtime.component_adapter.implementation import RuntimeClient

        self._client = RuntimeClient(
            runtime,
            source=source,
            target=target,
            component_contract_id=component_contract_id,
            request_codec_id=f"codec.python.{component_contract_id}.request.json",
        )
        self._component_contract_id = component_contract_id
        self._methods: dict[str, tuple[inspect.Signature, dict[str, object]]] = {}
        for spec in specs:
            protocol_method = inspect.getattr_static(protocol_type, spec.method_name, None)
            if protocol_method is None:
                raise RuntimeBindingInvalid(f"protocol has no method: {spec.method_name}")
            self._methods[spec.method_name] = (
                inspect.signature(protocol_method),
                get_type_hints(protocol_method),
            )
        self._failure_types = _exception_type_map(failure_types)
        self._bibliotek_runtime_proxy = True

    def __getattr__(self, name: str) -> Callable[..., object]:
        method = self._methods.get(name)
        if method is None:
            raise AttributeError(name)
        signature, hints = method

        def invoke(*args: object, **kwargs: object) -> object:
            bound = signature.bind(None, *args, **kwargs)
            bound.arguments.pop("self", None)
            bound.arguments.pop("cls", None)
            payload = cast(JsonObject, encode_json(dict(bound.arguments)))
            outcome = self._client.request_sync(f"{self._component_contract_id}.{name}", payload)
            response_payload = outcome.response.payload.value
            if not isinstance(response_payload, dict):
                raise RuntimeBindingInvalid("component response payload is not an object")
            if outcome.response.kind is RuntimeMessageKind.FAULT:
                failure_name = str(response_payload.get("type", "RuntimeBindingInvalid"))
                failure = self._failure_types.get(failure_name, RuntimeBindingInvalid)
                evidence = response_payload.get("evidence")
                raise _decode_failure(
                    failure,
                    str(response_payload.get("message", failure_name)),
                    cast(JsonObject, evidence) if isinstance(evidence, dict) else {},
                )
            return decode_typed(response_payload.get("result"), hints.get("return", NoneType))

        return invoke


def create_typed_proxy[T](
    runtime: MessageRuntime,
    source: RuntimeAddress,
    target: RuntimeAddress,
    protocol_type: type[T],
    *,
    component_contract_id: str,
    specs: tuple[MethodBindingSpec, ...],
    failure_types: tuple[type[Exception], ...],
) -> T:
    return cast(
        T,
        TypedMessageProxy(
            runtime,
            source,
            target,
            cast(type[object], protocol_type),
            component_contract_id=component_contract_id,
            specs=specs,
            failure_types=failure_types,
        ),
    )


def decode_typed(value: object, annotation: object) -> object:
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
