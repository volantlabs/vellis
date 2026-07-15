from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, cast, runtime_checkable
from uuid import UUID, uuid4

from components.runtime.component_adapter.protocol import (
    RuntimeActionBindingDescriptor,
    RuntimeBindingDescription,
    RuntimeBindingInvalid,
    RuntimeDispatchResult,
    RuntimeFailureBindingDescriptor,
    RuntimePayloadInvalid,
    RuntimeReplayStateStatus,
    RuntimeTerminalEncodingFailed,
)
from components.runtime.message_runtime.protocol import (
    JsonObject,
    JsonValue,
    MessageRuntime,
    RuntimeAddress,
    RuntimeMessageEnvelope,
    RuntimeMessageKind,
    RuntimePayload,
    RuntimeReplayMode,
    RuntimeRequestOutcome,
    RuntimeTraceDisposition,
)

type RequestDecoder = Callable[[JsonObject], tuple[tuple[object, ...], dict[str, object]]]
type ResultEncoder = Callable[[object], JsonValue]
type ReplayEffectBuilder = Callable[[tuple[object, ...], dict[str, object], object], JsonObject]
type ReplayEffectApplier = Callable[[JsonObject], object | Awaitable[object]]
type FailureReplayEffectBuilder = Callable[[Exception], JsonObject]
type EmptyStateProbe = Callable[[], bool | Awaitable[bool]]
type StateResetter = Callable[[], object | Awaitable[object]]
type CheckpointImporter = Callable[[str], int | Awaitable[int]]
type StateExporter = Callable[[], JsonValue | Awaitable[JsonValue]]
type StateVerifier = Callable[[], tuple[str, ...] | Awaitable[tuple[str, ...]]]
type ConfirmedCursor = Callable[[], int | None | Awaitable[int | None]]
type ConfirmedDigest = Callable[[], str | None | Awaitable[str | None]]


class MutableAdapterHost[T]:
    """Thread-safe private indirection for swapping an explicitly bound implementation."""

    def __init__(self, component: T) -> None:
        self._component = component
        self._lock = threading.RLock()

    def resolve(self) -> T:
        with self._lock:
            return self._component

    def replace(self, component: T) -> T:
        with self._lock:
            previous = self._component
            self._component = component
            return previous


@dataclass(frozen=True, slots=True)
class ActionBinding:
    descriptor: RuntimeActionBindingDescriptor
    invoke: Callable[..., object]
    decode_request: RequestDecoder
    encode_result: ResultEncoder
    failure_types: tuple[type[Exception], ...] = ()
    build_replay_effect: ReplayEffectBuilder | None = None
    apply_replay_effect: ReplayEffectApplier | None = None
    build_failure_replay_effect: FailureReplayEffectBuilder | None = None


@dataclass(frozen=True, slots=True)
class ReplayStateBinding:
    """Adapter-host SPI for safe reset, checkpoint import, digest, and verification."""

    is_empty: EmptyStateProbe
    reset: StateResetter
    import_checkpoint: CheckpointImporter
    export_state: StateExporter
    verify: StateVerifier = lambda: ()
    confirmed_cursor: ConfirmedCursor = lambda: None
    confirmed_digest: ConfirmedDigest = lambda: None


class ExplicitComponentAdapter:
    """Adapter with an explicit action inventory and no reflective method exposure."""

    def __init__(
        self,
        bindings: tuple[ActionBinding, ...],
        *,
        replay_state: ReplayStateBinding | None = None,
    ) -> None:
        if not bindings:
            raise RuntimeBindingInvalid("at least one explicit action binding is required")
        first = bindings[0].descriptor
        by_action: dict[str, ActionBinding] = {}
        normalized_bindings: list[ActionBinding] = []
        for binding in bindings:
            descriptor = _complete_descriptor(binding)
            binding = replace(binding, descriptor=descriptor)
            if descriptor.binding_id != first.binding_id or descriptor.binding_version != (
                first.binding_version
            ):
                raise RuntimeBindingInvalid("all actions must belong to one binding identity")
            if descriptor.component_contract_id != first.component_contract_id:
                raise RuntimeBindingInvalid("all actions must target one component contract")
            if descriptor.action_id in by_action:
                raise RuntimeBindingInvalid(f"duplicate action binding: {descriptor.action_id}")
            if descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT and (
                binding.build_replay_effect is None or binding.apply_replay_effect is None
            ):
                raise RuntimeBindingInvalid(
                    f"canonical-effect action lacks replay mapping: {descriptor.action_id}"
                )
            if any(
                failure.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
                for failure in descriptor.failure_bindings
            ) and (
                binding.build_failure_replay_effect is None or binding.apply_replay_effect is None
            ):
                raise RuntimeBindingInvalid(
                    f"canonical-effect failure lacks replay mapping: {descriptor.action_id}"
                )
            _validate_descriptor(descriptor)
            by_action[descriptor.action_id] = binding
            normalized_bindings.append(binding)
        self._bindings = by_action
        self._replay_state = replay_state
        self._description = RuntimeBindingDescription(
            binding_id=first.binding_id,
            binding_version=first.binding_version,
            actions=tuple(binding.descriptor for binding in normalized_bindings),
        )

    def describe(self) -> RuntimeBindingDescription:
        return self._description

    async def dispatch(self, request: RuntimeMessageEnvelope) -> RuntimeDispatchResult:
        binding = self._bindings.get(request.action_id)
        if binding is None:
            raise RuntimeBindingInvalid(f"unregistered action: {request.action_id}")
        descriptor = binding.descriptor
        if request.component_contract_id != descriptor.component_contract_id:
            raise RuntimeBindingInvalid("component contract ID does not match target binding")
        if request.schema_version != descriptor.schema_version:
            raise RuntimePayloadInvalid(
                f"unsupported schema version {request.schema_version} for {request.action_id}"
            )
        if request.payload.codec_id != descriptor.request_codec_id:
            raise RuntimePayloadInvalid(
                f"unsupported request codec {request.payload.codec_id} for {request.action_id}"
            )
        if request.payload.content_type != descriptor.request_content_type:
            raise RuntimePayloadInvalid(
                f"unsupported content type {request.payload.content_type} for {request.action_id}"
            )
        if request.payload.codec_version != descriptor.request_codec_version:
            raise RuntimePayloadInvalid(
                f"unsupported request codec version {request.payload.codec_version} "
                f"for {request.action_id}"
            )
        payload = request.payload.value
        if not isinstance(payload, dict):
            raise RuntimePayloadInvalid("request payload must be a JSON object")
        try:
            args, kwargs = binding.decode_request(cast(JsonObject, payload))
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimePayloadInvalid(str(error)) from error

        try:
            if inspect.iscoroutinefunction(binding.invoke):
                raw_result = await cast(Callable[..., Awaitable[object]], binding.invoke)(
                    *args, **kwargs
                )
            else:
                raw_result = await asyncio.to_thread(binding.invoke, *args, **kwargs)
        except binding.failure_types as error:
            failure_descriptor = next(
                (
                    item
                    for item in descriptor.failure_bindings
                    if item.failure_name
                    in {failure_type.__name__ for failure_type in type(error).mro()}
                ),
                None,
            )
            if failure_descriptor is None:
                raise RuntimeBindingInvalid(
                    f"modeled failure lacks a descriptor: {type(error).__name__}"
                ) from error
            try:
                response = _response_envelope(
                    request,
                    kind=RuntimeMessageKind.FAULT,
                    codec_id=failure_descriptor.codec_id,
                    codec_version=failure_descriptor.codec_version,
                    content_type=failure_descriptor.content_type,
                    value={
                        "type": type(error).__name__,
                        "message": str(error),
                        "evidence": _exception_evidence(error),
                    },
                )
                canonical_effect = None
                effect_digest = None
                if (
                    binding.build_failure_replay_effect is not None
                    and failure_descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
                ):
                    effect_payload = await asyncio.to_thread(
                        binding.build_failure_replay_effect, error
                    )
                    canonical_effect = _canonical_effect(descriptor, effect_payload)
                    effect_digest = hashlib.sha256(
                        _canonical_json(canonical_effect).encode()
                    ).hexdigest()
            except Exception as encoding_error:
                raise RuntimeTerminalEncodingFailed(
                    f"terminal fault encoding failed for {request.action_id}: {encoding_error}"
                ) from encoding_error
            return RuntimeDispatchResult(
                response=response,
                canonical_effect=canonical_effect,
                effect_digest=effect_digest,
                trace_disposition=failure_descriptor.trace_disposition,
            )
        except Exception as error:
            response = _response_envelope(
                request,
                kind=RuntimeMessageKind.FAULT,
                codec_id=descriptor.failure_codec_id,
                codec_version=descriptor.failure_codec_version,
                content_type=descriptor.failure_content_type,
                value={
                    "type": "RuntimeComponentFault",
                    "message": str(error),
                    "evidence": {"exception_type": type(error).__name__},
                },
            )
            return RuntimeDispatchResult(
                response=response,
                trace_disposition=RuntimeTraceDisposition.INDETERMINATE,
            )

        try:
            result_value = binding.encode_result(raw_result)
            response = _response_envelope(
                request,
                kind=RuntimeMessageKind.RESPONSE,
                codec_id=descriptor.result_codec_id,
                codec_version=descriptor.result_codec_version,
                content_type=descriptor.result_content_type,
                value={"result": result_value},
            )
            canonical_effect: JsonObject | None = None
            effect_digest: str | None = None
            if descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT:
                assert binding.build_replay_effect is not None
                effect_payload = binding.build_replay_effect(args, kwargs, raw_result)
                canonical_effect = _canonical_effect(descriptor, effect_payload)
                effect_digest = hashlib.sha256(
                    _canonical_json(canonical_effect).encode()
                ).hexdigest()
        except Exception as error:
            raise RuntimeTerminalEncodingFailed(
                f"terminal response encoding failed for {request.action_id}: {error}"
            ) from error
        return RuntimeDispatchResult(
            response=response,
            canonical_effect=canonical_effect,
            effect_digest=effect_digest,
            trace_disposition=RuntimeTraceDisposition.COMMITTED,
        )

    async def apply_replay_effect(self, effect: JsonObject) -> None:
        try:
            action_id = str(effect["action_id"])
            binding_id = str(effect["binding_id"])
            binding_version = int(cast(int | str, effect["binding_version"]))
            component_contract_id = str(effect["component_contract_id"])
            schema_version = int(cast(int | str, effect["schema_version"]))
            payload = effect["payload"]
            effect_schema_version = int(cast(int | str, effect["effect_schema_version"]))
            effect_codec_id = str(effect["effect_codec_id"])
            effect_codec_version = int(cast(int | str, effect["effect_codec_version"]))
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimePayloadInvalid(f"malformed canonical effect: {error}") from error
        binding = self._bindings.get(action_id)
        if binding is None:
            raise RuntimeBindingInvalid(f"canonical effect action is not registered: {action_id}")
        descriptor = binding.descriptor
        if binding_id != descriptor.binding_id or binding_version != descriptor.binding_version:
            raise RuntimeBindingInvalid(
                f"canonical effect binding mismatch for {action_id}: {binding_id}@{binding_version}"
            )
        if (
            component_contract_id != descriptor.component_contract_id
            or schema_version != descriptor.schema_version
        ):
            raise RuntimeBindingInvalid(
                f"canonical effect contract/schema mismatch for {action_id}: "
                f"{component_contract_id}@{schema_version}"
            )
        if (
            effect_schema_version != descriptor.canonical_effect_schema_version
            or effect_codec_id != descriptor.canonical_effect_codec_id
            or effect_codec_version != descriptor.canonical_effect_codec_version
        ):
            raise RuntimeBindingInvalid(
                f"canonical effect codec mismatch for {action_id}: "
                f"{effect_codec_id}@{effect_codec_version}/schema-{effect_schema_version}"
            )
        if binding.apply_replay_effect is None:
            raise RuntimeBindingInvalid(f"action has no canonical replay mapping: {action_id}")
        if not isinstance(payload, dict):
            raise RuntimePayloadInvalid("canonical effect payload must be a JSON object")
        if inspect.iscoroutinefunction(binding.apply_replay_effect):
            await cast(Callable[[JsonObject], Awaitable[object]], binding.apply_replay_effect)(
                cast(JsonObject, payload)
            )
        else:
            applied = await asyncio.to_thread(
                binding.apply_replay_effect, cast(JsonObject, payload)
            )
            if inspect.isawaitable(applied):
                await cast(Awaitable[object], applied)

    async def replay_state_status(self) -> RuntimeReplayStateStatus:
        if self._replay_state is None:
            return RuntimeReplayStateStatus(
                available=False,
                empty=False,
                limitations=("binding does not provide replay-state inspection",),
            )
        empty = cast(bool, await _invoke_callback(self._replay_state.is_empty))
        cursor = cast(int | None, await _invoke_callback(self._replay_state.confirmed_cursor))
        digest = cast(str | None, await _invoke_callback(self._replay_state.confirmed_digest))
        return RuntimeReplayStateStatus(
            available=True,
            empty=empty,
            prepared=cursor is not None and digest is not None,
            checkpoint_cursor=cursor or 0,
            state_digest=digest,
        )

    async def reset_replay_state(self) -> None:
        if self._replay_state is None:
            raise RuntimeBindingInvalid("binding does not provide replay-state reset")
        await _invoke_callback(self._replay_state.reset)

    async def import_replay_checkpoint(self, reference: str) -> int:
        if self._replay_state is None:
            raise RuntimeBindingInvalid("binding does not provide checkpoint import")
        cursor = await _invoke_callback(self._replay_state.import_checkpoint, reference)
        return int(cast(int, cursor))

    async def replay_state_digest(self) -> str:
        if self._replay_state is None:
            raise RuntimeBindingInvalid("binding does not provide replay-state export")
        state = cast(JsonValue, await _invoke_callback(self._replay_state.export_state))
        return hashlib.sha256(_canonical_json(state).encode()).hexdigest()

    async def verify_replay_state(self) -> tuple[str, ...]:
        if self._replay_state is None:
            return ("binding does not provide replay-state verification",)
        result = await _invoke_callback(self._replay_state.verify)
        return tuple(cast(tuple[str, ...], result))


@runtime_checkable
class _SyncRuntime(Protocol):
    def request_sync(
        self, message: RuntimeMessageEnvelope, timeout_seconds: float | None = None
    ) -> RuntimeRequestOutcome: ...

    def current_envelope(self) -> RuntimeMessageEnvelope | None: ...


class RuntimeClient:
    """Message client used by generated or hand-authored component proxies."""

    def __init__(
        self,
        runtime: MessageRuntime,
        *,
        source: RuntimeAddress,
        target: RuntimeAddress,
        component_contract_id: str,
        request_codec_id: str,
        codec_version: int = 1,
        schema_version: int = 1,
    ) -> None:
        self._runtime = runtime
        self._source = source
        self._target = target
        self._component_contract_id = component_contract_id
        self._request_codec_id = request_codec_id
        self._codec_version = codec_version
        self._schema_version = schema_version

    def envelope(
        self,
        action_id: str,
        arguments: JsonObject,
        *,
        message_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> RuntimeMessageEnvelope:
        current = None
        if isinstance(self._runtime, _SyncRuntime):
            current = self._runtime.current_envelope()
        trace_id = current.trace_id if current else uuid4()
        correlation_id = current.correlation_id or current.message_id if current else None
        return RuntimeMessageEnvelope(
            message_id=message_id or uuid4(),
            kind=RuntimeMessageKind.REQUEST,
            source=self._source,
            target=self._target,
            component_contract_id=self._component_contract_id,
            action_id=action_id,
            schema_version=self._schema_version,
            trace_id=trace_id,
            correlation_id=correlation_id,
            causation_id=current.message_id if current else None,
            idempotency_key=idempotency_key,
            created_at=_now(),
            payload=RuntimePayload(
                content_type="application/json",
                codec_id=self._request_codec_id,
                codec_version=self._codec_version,
                value=arguments,
            ),
        )

    async def request(
        self,
        action_id: str,
        arguments: JsonObject,
        *,
        timeout_seconds: float | None = None,
        message_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> RuntimeRequestOutcome:
        return await self._runtime.request(
            self.envelope(
                action_id,
                arguments,
                message_id=message_id,
                idempotency_key=idempotency_key,
            ),
            timeout_seconds,
        )

    def request_sync(
        self,
        action_id: str,
        arguments: JsonObject,
        *,
        timeout_seconds: float | None = None,
        message_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> RuntimeRequestOutcome:
        runtime = cast(_SyncRuntime, self._runtime)
        return runtime.request_sync(
            self.envelope(
                action_id,
                arguments,
                message_id=message_id,
                idempotency_key=idempotency_key,
            ),
            timeout_seconds,
        )


def encode_json(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return cast(str, value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: encode_json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): encode_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set | frozenset):
        return [encode_json(item) for item in value]
    raise TypeError(f"value is not canonically JSON encodable: {type(value).__name__}")


def _response_envelope(
    request: RuntimeMessageEnvelope,
    *,
    kind: RuntimeMessageKind,
    codec_id: str,
    codec_version: int,
    content_type: str,
    value: JsonValue,
) -> RuntimeMessageEnvelope:
    return RuntimeMessageEnvelope(
        message_id=uuid4(),
        kind=kind,
        source=request.target,
        target=request.source,
        component_contract_id=request.component_contract_id,
        action_id=request.action_id,
        schema_version=request.schema_version,
        trace_id=request.trace_id,
        correlation_id=request.message_id,
        causation_id=request.message_id,
        created_at=_now(),
        payload=RuntimePayload(
            content_type=content_type,
            codec_id=codec_id,
            codec_version=codec_version,
            value=value,
        ),
    )


def _complete_descriptor(binding: ActionBinding) -> RuntimeActionBindingDescriptor:
    descriptor = binding.descriptor
    failures = descriptor.supported_failure_names or tuple(
        failure.__name__ for failure in binding.failure_types
    )
    failure_bindings = descriptor.failure_bindings or tuple(
        RuntimeFailureBindingDescriptor(
            failure_name=failure_name,
            codec_id=descriptor.failure_codec_id,
            codec_version=descriptor.failure_codec_version,
            content_type=descriptor.failure_content_type,
            trace_disposition=descriptor.modeled_fault_trace_disposition,
            replay_mode=(
                RuntimeReplayMode.CANONICAL_EFFECT
                if binding.build_failure_replay_effect is not None
                else RuntimeReplayMode.NO_STATE_EFFECT
            ),
        )
        for failure_name in failures
    )
    if (
        descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
        or binding.build_failure_replay_effect is not None
    ):
        effect_schema_version = descriptor.canonical_effect_schema_version or 1
        effect_codec_id = (
            descriptor.canonical_effect_codec_id
            or f"{descriptor.binding_id}.{descriptor.action_id}.effect.json"
        )
        effect_codec_version = descriptor.canonical_effect_codec_version or 1
    else:
        effect_schema_version = descriptor.canonical_effect_schema_version
        effect_codec_id = descriptor.canonical_effect_codec_id
        effect_codec_version = descriptor.canonical_effect_codec_version
    return replace(
        descriptor,
        supported_failure_names=failures,
        failure_bindings=failure_bindings,
        canonical_effect_schema_version=effect_schema_version,
        canonical_effect_codec_id=effect_codec_id,
        canonical_effect_codec_version=effect_codec_version,
    )


def _canonical_effect(
    descriptor: RuntimeActionBindingDescriptor, payload: JsonObject
) -> JsonObject:
    return {
        "binding_id": descriptor.binding_id,
        "binding_version": descriptor.binding_version,
        "component_contract_id": descriptor.component_contract_id,
        "action_id": descriptor.action_id,
        "schema_version": descriptor.schema_version,
        "effect_schema_version": descriptor.canonical_effect_schema_version,
        "effect_codec_id": descriptor.canonical_effect_codec_id,
        "effect_codec_version": descriptor.canonical_effect_codec_version,
        "payload": payload,
    }


def _validate_descriptor(descriptor: RuntimeActionBindingDescriptor) -> None:
    if any(
        version < 1
        for version in (
            descriptor.binding_version,
            descriptor.schema_version,
            descriptor.request_codec_version,
            descriptor.result_codec_version,
            descriptor.failure_codec_version,
            descriptor.max_in_flight,
        )
    ):
        raise RuntimeBindingInvalid(
            "binding, schema, codec, and concurrency versions must be positive"
        )
    if descriptor.concurrency_lane == "serialized" and descriptor.max_in_flight != 1:
        raise RuntimeBindingInvalid("serialized actions must declare max_in_flight=1")
    if descriptor.recovery_authorized and (
        descriptor.replay_mode is not RuntimeReplayMode.COORDINATOR_TRACE
        or descriptor.externally_effectful
    ):
        raise RuntimeBindingInvalid(
            "recovery-authorized actions must be non-effectful coordinator actions"
        )
    if tuple(item.failure_name for item in descriptor.failure_bindings) != (
        descriptor.supported_failure_names
    ):
        raise RuntimeBindingInvalid(
            "supported failure names and per-failure descriptors must match in order"
        )
    if any(
        not failure.failure_name.strip()
        or not failure.codec_id.strip()
        or not failure.content_type.strip()
        or failure.codec_version < 1
        for failure in descriptor.failure_bindings
    ):
        raise RuntimeBindingInvalid("failure descriptor identity and codec must be valid")
    if not all(
        value.strip()
        for value in (
            descriptor.request_content_type,
            descriptor.result_content_type,
            descriptor.failure_content_type,
            descriptor.request_codec_id,
            descriptor.result_codec_id,
            descriptor.failure_codec_id,
        )
    ):
        raise RuntimeBindingInvalid("binding content types and codec identities must be non-empty")
    has_canonical_replay = descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT or any(
        failure.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
        for failure in descriptor.failure_bindings
    )
    if has_canonical_replay:
        if (
            descriptor.canonical_effect_schema_version is None
            or descriptor.canonical_effect_codec_id is None
            or descriptor.canonical_effect_codec_version is None
        ):
            raise RuntimeBindingInvalid(
                "canonical replay actions require an effect schema and codec"
            )
    elif any(
        value is not None
        for value in (
            descriptor.canonical_effect_schema_version,
            descriptor.canonical_effect_codec_id,
            descriptor.canonical_effect_codec_version,
        )
    ):
        raise RuntimeBindingInvalid(
            "actions without canonical replay cannot declare an effect schema or codec"
        )


async def _invoke_callback(
    callback: Callable[..., object | Awaitable[object]], *args: object
) -> object:
    if inspect.iscoroutinefunction(callback):
        return await cast(Callable[..., Awaitable[object]], callback)(*args)
    value = await asyncio.to_thread(callback, *args)
    if inspect.isawaitable(value):
        return await cast(Awaitable[object], value)
    return value


def _exception_evidence(error: Exception) -> JsonObject:
    evidence: JsonObject = {}
    for name in ("transaction_id", "validation_report", "diagnostic"):
        if hasattr(error, name):
            encoded = encode_json(getattr(error, name))
            evidence[name] = encoded
    return evidence


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
