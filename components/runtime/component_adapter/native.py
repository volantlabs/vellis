from __future__ import annotations

import asyncio
import hashlib
import inspect
import threading
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4, uuid5

from components.runtime.messaging import (
    ActionRef,
    JsonObject,
    JsonValue,
    RuntimeActionBindingDescriptor,
    RuntimeAddress,
    RuntimeCanonicalEffectReference,
    RuntimeDeliveryStatus,
    RuntimeDeliveryUnknown,
    RuntimeFailureBindingDescriptor,
    RuntimeMessageConflict,
    RuntimeMessageEnvelope,
    RuntimeMessageKind,
    RuntimeMessageOutcome,
    RuntimeMessageReceipt,
    RuntimeParticipant,
    RuntimeParticipantContext,
    RuntimePayload,
    RuntimeReplayIncompatible,
    RuntimeReplayMode,
    RuntimeRequestIndeterminate,
    RuntimeRequestOutcome,
    RuntimeRequestTimedOut,
    RuntimeTraceDisposition,
    canonical_json,
    encode_json,
)

type RequestDecoder = Callable[[JsonObject], tuple[tuple[object, ...], dict[str, object]]]
type ResultEncoder = Callable[[object], JsonValue]
type ReplayEffectBuilder = Callable[[tuple[object, ...], dict[str, object], object], JsonObject]
type ReplayEffectApplier = Callable[[JsonObject], object | Awaitable[object]]
type FailureReplayEffectBuilder = Callable[[Exception], JsonObject]
type ActionHandler = Callable[
    [tuple[object, ...], dict[str, object], ComponentExecution], Awaitable[None]
]
type EmptyStateProbe = Callable[[], bool | Awaitable[bool]]
type StateResetter = Callable[[], object | Awaitable[object]]
type CheckpointImporter = Callable[[str], int | Awaitable[int]]
type StateExporter = Callable[[], JsonValue | Awaitable[JsonValue]]
type StateVerifier = Callable[[], tuple[str, ...] | Awaitable[tuple[str, ...]]]
type ConfirmedCursor = Callable[[], int | None | Awaitable[int | None]]
type ConfirmedDigest = Callable[[], str | None | Awaitable[str | None]]


class RuntimeBindingInvalid(Exception):
    """A binding descriptor, action registration, or component is invalid."""


class RuntimePayloadInvalid(Exception):
    """A request, response, fault, or replay payload cannot be decoded."""


class RuntimeTerminalEncodingFailed(Exception):
    """A terminal response or canonical effect cannot be encoded."""


class RuntimeRemoteFault(Exception):
    """A correlated component call returned a modeled fault envelope."""

    def __init__(self, payload: JsonObject) -> None:
        self.payload = payload
        super().__init__(str(payload.get("message", payload.get("type", "remote fault"))))


@dataclass(frozen=True, slots=True)
class RuntimeBindingDescription:
    binding_id: str
    binding_version: int
    component_contract_id: str
    actions: tuple[RuntimeActionBindingDescriptor, ...]


@dataclass(frozen=True, slots=True)
class RuntimeReplayStateStatus:
    available: bool
    empty: bool
    prepared: bool = False
    checkpoint_cursor: int = 0
    state_digest: str | None = None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionBinding:
    descriptor: RuntimeActionBindingDescriptor
    decode_request: RequestDecoder
    encode_result: ResultEncoder
    invoke: Callable[..., object] | None = None
    handler: ActionHandler | None = None
    failure_types: tuple[type[Exception], ...] = ()
    build_replay_effect: ReplayEffectBuilder | None = None
    apply_replay_effect: ReplayEffectApplier | None = None
    build_failure_replay_effect: FailureReplayEffectBuilder | None = None


@dataclass(frozen=True, slots=True)
class ReplayStateBinding:
    is_empty: EmptyStateProbe
    reset: StateResetter
    import_checkpoint: CheckpointImporter
    export_state: StateExporter
    verify: StateVerifier = lambda: ()
    confirmed_cursor: ConfirmedCursor = lambda: None
    confirmed_digest: ConfirmedDigest = lambda: None


@dataclass(slots=True)
class _Continuation:
    message_id: UUID
    request_identity: str
    owner_execution_id: UUID | None
    future: Future[tuple[RuntimeMessageEnvelope, RuntimeMessageReceipt]]
    waiters: int = 0


@dataclass(slots=True)
class _StepCall:
    request_identity: str
    continuation: _Continuation


class MessageSender(Protocol):
    async def send(self, message: RuntimeMessageEnvelope) -> RuntimeMessageReceipt: ...

    async def lookup_message_outcome(self, message_id: UUID) -> RuntimeMessageOutcome | None: ...


class ComponentExecution:
    """One ordinary component action execution, whether local or coordinating."""

    def __init__(
        self,
        adapter: ComponentAdapter,
        binding: ActionBinding,
        envelope: RuntimeMessageEnvelope,
        context: RuntimeParticipantContext,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        deadline_at: float | None,
    ) -> None:
        self._adapter = adapter
        self._binding = binding
        self._envelope = envelope
        self._context = context
        self._args = args
        self._kwargs = kwargs
        self._deadline_at = deadline_at
        self._completed = False
        self._steps: dict[str, _StepCall] = {}

    @property
    def request(self) -> RuntimeMessageEnvelope:
        return self._envelope

    @property
    def completed(self) -> bool:
        return self._completed

    @property
    def remaining_seconds(self) -> float | None:
        if self._deadline_at is None:
            return None
        return max(0.0, self._deadline_at - asyncio.get_running_loop().time())

    def address_for(self, instance_key: str) -> RuntimeAddress:
        return self._context.address_for(instance_key)

    async def send(
        self,
        action: ActionRef,
        arguments: Mapping[str, object],
        *,
        target: RuntimeAddress,
        kind: RuntimeMessageKind = RuntimeMessageKind.SIGNAL,
        step_key: str | None = None,
        idempotency_key: str | None = None,
    ) -> RuntimeMessageReceipt:
        message_id = uuid5(self._envelope.message_id, step_key) if step_key is not None else uuid4()
        return await self._context.send(
            action,
            cast(JsonObject, encode_json(dict(arguments))),
            target=target,
            kind=kind,
            message_id=message_id,
            idempotency_key=idempotency_key,
        )

    async def call(
        self,
        step_key: str,
        action: ActionRef,
        arguments: Mapping[str, object],
        *,
        target: RuntimeAddress,
        timeout_seconds: float | None = None,
        idempotency_key: str | None = None,
    ) -> JsonValue:
        message_id = uuid5(self._envelope.message_id, step_key)
        encoded_arguments = cast(JsonObject, encode_json(dict(arguments)))
        request_identity = canonical_json(
            {
                "action": action,
                "arguments": encoded_arguments,
                "target": target,
                "idempotency_key": idempotency_key,
            }
        )
        step = self._steps.get(step_key)
        if step is not None and step.request_identity != request_identity:
            raise RuntimeMessageConflict(str(message_id))
        if step is None:
            continuation = self._adapter._open_continuation(
                message_id,
                request_identity=request_identity,
                owner_execution_id=self._envelope.message_id,
            )
            self._steps[step_key] = _StepCall(request_identity, continuation)
            try:
                await self._context.send(
                    action,
                    encoded_arguments,
                    target=target,
                    kind=RuntimeMessageKind.REQUEST,
                    message_id=message_id,
                    idempotency_key=idempotency_key,
                )
            except Exception:
                self._adapter._discard_continuation(message_id)
                self._steps.pop(step_key, None)
                raise
        else:
            continuation = step.continuation
        response, _ = await _await_continuation(continuation, timeout_seconds, message_id)
        payload = response.payload.value
        if not isinstance(payload, dict):
            raise RuntimePayloadInvalid("component response payload must be an object")
        if response.kind is RuntimeMessageKind.FAULT:
            raise RuntimeRemoteFault(cast(JsonObject, payload))
        return payload.get("result")

    async def effect_reference(self, step_key: str) -> RuntimeCanonicalEffectReference:
        """Resolve a recorded effect only for a deterministic completed child step."""
        step = self._steps.get(step_key)
        if step is None or not step.continuation.future.done():
            raise RuntimeReplayIncompatible(f"step is not complete: {step_key}")
        return await self._context.canonical_effect_reference(step.continuation.message_id)

    def superseding_aggregate_effect(
        self, references: tuple[RuntimeCanonicalEffectReference, ...]
    ) -> JsonObject:
        if not references:
            raise RuntimeReplayIncompatible("superseding aggregate requires an effect reference")
        return _canonical_effect(
            self._binding.descriptor,
            {
                "supersedes_trace_effects": True,
                "canonical_effect_references": [encode_json(item) for item in references],
            },
        )

    async def complete(
        self,
        result: object,
        *,
        canonical_effect: JsonObject | None = None,
    ) -> RuntimeMessageReceipt:
        self._require_open()
        binding = self._binding
        descriptor = binding.descriptor
        try:
            result_value = binding.encode_result(result)
            if (
                canonical_effect is None
                and descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
            ):
                if binding.build_replay_effect is None:
                    raise RuntimeBindingInvalid(
                        f"canonical action lacks effect builder: {descriptor.action_id}"
                    )
                canonical_effect = _canonical_effect(
                    descriptor,
                    binding.build_replay_effect(self._args, self._kwargs, result),
                )
            effect_digest = _effect_digest(canonical_effect)
            receipt = await self._context.complete(
                self._envelope.message_id,
                RuntimePayload(
                    codec_id=descriptor.result_codec_id,
                    codec_version=descriptor.result_codec_version,
                    content_type=descriptor.result_content_type,
                    value={"result": result_value},
                ),
                canonical_effect=canonical_effect,
                effect_digest=effect_digest,
            )
        except Exception as error:
            raise RuntimeTerminalEncodingFailed(
                f"terminal response encoding failed for {descriptor.action_id}: {error}"
            ) from error
        self._completed = True
        return receipt

    async def forward_fault(
        self,
        payload: JsonObject,
        *,
        disposition: RuntimeTraceDisposition = RuntimeTraceDisposition.ABORTED,
        canonical_effect: JsonObject | None = None,
    ) -> RuntimeMessageReceipt:
        """Finish this request with an already encoded collaborator fault."""
        self._require_open()
        descriptor = self._binding.descriptor
        receipt = await self._context.fault(
            self._envelope.message_id,
            RuntimePayload(
                codec_id=descriptor.failure_codec_id,
                codec_version=descriptor.failure_codec_version,
                content_type=descriptor.failure_content_type,
                value=payload,
            ),
            trace_disposition=disposition,
            canonical_effect=canonical_effect,
            effect_digest=_effect_digest(canonical_effect),
        )
        self._completed = True
        return receipt

    async def ack(
        self,
        *,
        canonical_effect: JsonObject | None = None,
    ) -> RuntimeMessageReceipt:
        """Acknowledge this inbound signal through the uniform delivery path."""
        self._require_open()
        receipt = await self._context.ack(
            self._envelope.message_id,
            canonical_effect=canonical_effect,
            effect_digest=_effect_digest(canonical_effect),
        )
        self._completed = True
        return receipt

    async def fault(
        self,
        error: Exception,
        *,
        canonical_effect: JsonObject | None = None,
        disposition: RuntimeTraceDisposition | None = None,
    ) -> RuntimeMessageReceipt:
        self._require_open()
        descriptor = self._binding.descriptor
        failure = _failure_descriptor(descriptor, error)
        if failure is None:
            fault_type = type(error).__name__
            disposition = disposition or RuntimeTraceDisposition.INDETERMINATE
            codec_id = descriptor.failure_codec_id
            codec_version = descriptor.failure_codec_version
            content_type = descriptor.failure_content_type
        else:
            fault_type = type(error).__name__
            disposition = disposition or failure.trace_disposition
            codec_id = failure.codec_id
            codec_version = failure.codec_version
            content_type = failure.content_type
            if (
                canonical_effect is None
                and failure.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT
            ):
                builder = self._binding.build_failure_replay_effect
                if builder is None:
                    raise RuntimeBindingInvalid(
                        f"modeled fault lacks effect builder: {descriptor.action_id}"
                    )
                canonical_effect = _canonical_effect(descriptor, builder(error))
        receipt = await self._context.fault(
            self._envelope.message_id,
            RuntimePayload(
                codec_id=codec_id,
                codec_version=codec_version,
                content_type=content_type,
                value={
                    "type": fault_type,
                    "message": str(error),
                    "evidence": _exception_evidence(error),
                },
            ),
            trace_disposition=cast(RuntimeTraceDisposition, disposition),
            canonical_effect=canonical_effect,
            effect_digest=_effect_digest(canonical_effect),
        )
        self._completed = True
        return receipt

    def _require_open(self) -> None:
        if self._completed:
            raise RuntimeDeliveryUnknown(str(self._envelope.message_id))


class ComponentAdapter(RuntimeParticipant):
    """Standard composable participant for every Bibliotek component role."""

    def __init__(
        self,
        bindings: tuple[ActionBinding, ...] = (),
        *,
        binding_id: str | None = None,
        binding_version: int = 1,
        component_contract_id: str | None = None,
        replay_state: ReplayStateBinding | None = None,
        max_outstanding_calls: int = 256,
    ) -> None:
        if not bindings and (not binding_id or not component_contract_id):
            raise RuntimeBindingInvalid(
                "an actionless adapter requires binding and component contract identities"
            )
        normalized: list[ActionBinding] = []
        by_action: dict[str, ActionBinding] = {}
        first = bindings[0].descriptor if bindings else None
        resolved_binding_id = binding_id or cast(RuntimeActionBindingDescriptor, first).binding_id
        resolved_contract_id = (
            component_contract_id
            or cast(RuntimeActionBindingDescriptor, first).component_contract_id
        )
        resolved_binding_version = (
            cast(RuntimeActionBindingDescriptor, first).binding_version
            if first is not None
            else binding_version
        )
        for binding in bindings:
            completed = replace(binding, descriptor=_complete_descriptor(binding))
            descriptor = completed.descriptor
            if descriptor.binding_id != resolved_binding_id:
                raise RuntimeBindingInvalid("all actions must use one binding identity")
            if descriptor.binding_version != resolved_binding_version:
                raise RuntimeBindingInvalid("all actions must use one binding version")
            if descriptor.component_contract_id != resolved_contract_id:
                raise RuntimeBindingInvalid("all actions must use one component contract")
            if descriptor.action_id in by_action:
                raise RuntimeBindingInvalid(f"duplicate action binding: {descriptor.action_id}")
            if completed.invoke is None and completed.handler is None:
                raise RuntimeBindingInvalid(f"action has no handler: {descriptor.action_id}")
            _validate_descriptor(descriptor, completed)
            by_action[descriptor.action_id] = completed
            normalized.append(completed)
        if max_outstanding_calls < 1:
            raise RuntimeBindingInvalid("max_outstanding_calls must be positive")
        self._bindings = by_action
        self._replay_state = replay_state
        self._max_outstanding_calls = max_outstanding_calls
        self._continuations: dict[UUID, _Continuation] = {}
        self._continuation_lock = threading.RLock()
        self._description = RuntimeBindingDescription(
            binding_id=resolved_binding_id,
            binding_version=resolved_binding_version,
            component_contract_id=resolved_contract_id,
            actions=tuple(item.descriptor for item in normalized),
        )

    def describe(self) -> RuntimeBindingDescription:
        return self._description

    async def deliver(
        self,
        envelope: RuntimeMessageEnvelope,
        context: RuntimeParticipantContext,
    ) -> None:
        if envelope.kind in {RuntimeMessageKind.RESPONSE, RuntimeMessageKind.FAULT}:
            await self._deliver_terminal(envelope, context)
            return
        binding = self._bindings.get(envelope.action_id)
        if binding is None:
            raise RuntimeBindingInvalid(f"unregistered action: {envelope.action_id}")
        payload = envelope.payload.value
        if not isinstance(payload, dict):
            raise RuntimePayloadInvalid("request payload must be an object")
        try:
            args, kwargs = binding.decode_request(cast(JsonObject, payload))
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimePayloadInvalid(str(error)) from error

        if envelope.kind is RuntimeMessageKind.SIGNAL:
            await self._invoke_signal(binding, args, kwargs, envelope, context)
            return

        deadline = binding.descriptor.deadline_seconds
        deadline_at = asyncio.get_running_loop().time() + deadline if deadline is not None else None
        execution = ComponentExecution(self, binding, envelope, context, args, kwargs, deadline_at)
        try:
            await self._invoke_request(binding, args, kwargs, execution)
        except asyncio.CancelledError:
            raise
        except RuntimeComponentDeadlineExceeded as error:
            if not execution.completed:
                await execution.fault(
                    error,
                    disposition=RuntimeTraceDisposition.ABORTED,
                )
        except binding.failure_types as error:
            if not execution.completed:
                await execution.fault(error)
        except Exception as error:
            if not execution.completed:
                await execution.fault(error, disposition=RuntimeTraceDisposition.INDETERMINATE)
        if not execution.completed:
            raise RuntimeDeliveryUnknown(
                f"handler returned without completing request {envelope.message_id}"
            )

    async def _invoke_request(
        self,
        binding: ActionBinding,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        execution: ComponentExecution,
    ) -> None:
        if binding.handler is not None:
            await binding.handler(args, kwargs, execution)
            return
        assert binding.invoke is not None
        result = await _invoke_callable(binding.invoke, *args, **kwargs)
        await execution.complete(result)

    async def _invoke_signal(
        self,
        binding: ActionBinding,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        envelope: RuntimeMessageEnvelope,
        context: RuntimeParticipantContext,
    ) -> None:
        effect: JsonObject | None = None
        if binding.handler is not None:
            execution = ComponentExecution(
                self,
                binding,
                envelope,
                context,
                args,
                kwargs,
                None,
            )
            await binding.handler(args, kwargs, execution)
            if not execution.completed:
                raise RuntimeDeliveryUnknown(
                    f"handler returned without acknowledging signal {envelope.message_id}"
                )
            return
        assert binding.invoke is not None
        result = await _invoke_callable(binding.invoke, *args, **kwargs)
        if binding.descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT:
            if binding.build_replay_effect is None:
                raise RuntimeBindingInvalid("canonical signal lacks effect builder")
            effect = _canonical_effect(
                binding.descriptor,
                binding.build_replay_effect(args, kwargs, result),
            )
        await context.ack(
            envelope.message_id,
            canonical_effect=effect,
            effect_digest=_effect_digest(effect),
        )

    async def _deliver_terminal(
        self,
        envelope: RuntimeMessageEnvelope,
        context: RuntimeParticipantContext,
    ) -> None:
        correlation_id = envelope.correlation_id
        if correlation_id is None:
            raise RuntimePayloadInvalid("response or fault lacks correlation_id")
        receipt = await context.ack(envelope.message_id)
        with self._continuation_lock:
            continuation = self._continuations.pop(correlation_id, None)
        if continuation is None:
            return
        if not continuation.future.done():
            continuation.future.set_result((envelope, receipt))

    def _open_continuation(
        self,
        message_id: UUID,
        *,
        request_identity: str,
        owner_execution_id: UUID | None,
    ) -> _Continuation:
        with self._continuation_lock:
            existing = self._continuations.get(message_id)
            if existing is not None:
                if existing.request_identity != request_identity:
                    raise RuntimeMessageConflict(str(message_id))
                return existing
            if len(self._continuations) >= self._max_outstanding_calls:
                raise RuntimeBindingInvalid("component outstanding-call limit reached")
            continuation = _Continuation(
                message_id,
                request_identity,
                owner_execution_id,
                Future(),
            )
            self._continuations[message_id] = continuation
            return continuation

    def _discard_continuation(self, message_id: UUID) -> None:
        with self._continuation_lock:
            self._continuations.pop(message_id, None)

    def _continuation_for(self, message_id: UUID) -> _Continuation | None:
        with self._continuation_lock:
            return self._continuations.get(message_id)

    async def apply_replay_effect(self, effect: JsonObject) -> None:
        action_id, payload = _validate_effect_identity(effect, self._bindings)
        binding = self._bindings[action_id]
        if binding.apply_replay_effect is None:
            raise RuntimeBindingInvalid(f"action has no replay mapping: {action_id}")
        await _invoke_callable(binding.apply_replay_effect, payload)

    async def replay_state_status(self) -> RuntimeReplayStateStatus:
        if self._replay_state is None:
            return RuntimeReplayStateStatus(
                available=False,
                empty=True,
                limitations=("binding owns no replay state",),
            )
        empty = cast(bool, await _invoke_callable(self._replay_state.is_empty))
        cursor = cast(int | None, await _invoke_callable(self._replay_state.confirmed_cursor))
        digest = cast(str | None, await _invoke_callable(self._replay_state.confirmed_digest))
        return RuntimeReplayStateStatus(
            available=True,
            empty=empty,
            prepared=cursor is not None and digest is not None,
            checkpoint_cursor=cursor or 0,
            state_digest=digest,
        )

    async def reset_replay_state(self) -> None:
        if self._replay_state is None:
            raise RuntimeBindingInvalid("binding owns no replay state")
        await _invoke_callable(self._replay_state.reset)

    async def import_replay_checkpoint(self, reference: str) -> int:
        if self._replay_state is None:
            raise RuntimeBindingInvalid("binding owns no replay state")
        return int(
            cast(int, await _invoke_callable(self._replay_state.import_checkpoint, reference))
        )

    async def replay_state_digest(self) -> str:
        if self._replay_state is None:
            return hashlib.sha256(b"null").hexdigest()
        value = cast(JsonValue, await _invoke_callable(self._replay_state.export_state))
        return hashlib.sha256(canonical_json(value).encode()).hexdigest()

    async def verify_replay_state(self) -> tuple[str, ...]:
        if self._replay_state is None:
            return ()
        return tuple(cast(tuple[str, ...], await _invoke_callable(self._replay_state.verify)))


class ComponentEndpoint:
    """Loop-agnostic root ingress owned by any attached component occurrence."""

    def __init__(
        self,
        sender: MessageSender,
        adapter: ComponentAdapter,
        *,
        source: RuntimeAddress,
    ) -> None:
        self._sender = sender
        self._adapter = adapter
        self._source = source

    @property
    def source(self) -> RuntimeAddress:
        return self._source

    async def request(
        self,
        action: ActionRef,
        arguments: Mapping[str, object],
        *,
        target: RuntimeAddress,
        timeout_seconds: float | None = None,
        message_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> RuntimeRequestOutcome:
        resolved_message_id = message_id or uuid4()
        candidate = _request_envelope(
            action,
            cast(JsonObject, encode_json(dict(arguments))),
            source=self._source,
            target=target,
            message_id=resolved_message_id,
            trace_id=uuid4(),
            idempotency_key=idempotency_key,
        )
        request_identity = _request_identity(candidate)
        recorded = await self._sender.lookup_message_outcome(resolved_message_id)
        envelope = candidate
        if recorded is not None:
            envelope = recorded.request_envelope
            if _request_identity(envelope) != request_identity:
                raise RuntimeMessageConflict(str(resolved_message_id))
            if (
                recorded.terminal_envelope is not None
                and recorded.terminal_receipt is not None
                and recorded.terminal_receipt.terminal_position is not None
            ):
                return _request_outcome(
                    recorded.request_receipt,
                    recorded.terminal_envelope,
                    recorded.terminal_receipt,
                )
            if recorded.request_receipt.status is RuntimeDeliveryStatus.INDETERMINATE:
                raise RuntimeRequestIndeterminate(resolved_message_id)
        continuation = self._adapter._continuation_for(resolved_message_id)
        if continuation is None:
            continuation = self._adapter._open_continuation(
                resolved_message_id,
                request_identity=request_identity,
                owner_execution_id=None,
            )
        try:
            receipt = await self._sender.send(envelope)
        except Exception:
            if recorded is None:
                self._adapter._discard_continuation(resolved_message_id)
            raise
        response, terminal_receipt = await _await_continuation(
            continuation, timeout_seconds, resolved_message_id
        )
        return _request_outcome(receipt, response, terminal_receipt)

    async def signal(
        self,
        action: ActionRef,
        arguments: Mapping[str, object],
        *,
        target: RuntimeAddress,
        message_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> RuntimeMessageReceipt:
        resolved_message_id = message_id or uuid4()
        return await self._sender.send(
            _request_envelope(
                action,
                cast(JsonObject, encode_json(dict(arguments))),
                source=self._source,
                target=target,
                message_id=resolved_message_id,
                trace_id=uuid4(),
                kind=RuntimeMessageKind.SIGNAL,
                idempotency_key=idempotency_key,
            )
        )


class RuntimeComponentDeadlineExceeded(Exception):
    def __init__(self, action_id: str) -> None:
        super().__init__(f"component action deadline exceeded: {action_id}")


async def _await_continuation(
    continuation: _Continuation,
    timeout_seconds: float | None,
    message_id: UUID,
) -> tuple[RuntimeMessageEnvelope, RuntimeMessageReceipt]:
    continuation.waiters += 1
    try:
        future = asyncio.wrap_future(continuation.future)
        if timeout_seconds is None:
            return await asyncio.shield(future)
        try:
            async with asyncio.timeout(timeout_seconds):
                return await asyncio.shield(future)
        except TimeoutError as error:
            raise RuntimeRequestTimedOut(message_id) from error
    finally:
        continuation.waiters -= 1


def _request_outcome(
    receipt: RuntimeMessageReceipt,
    response: RuntimeMessageEnvelope,
    terminal: RuntimeMessageReceipt,
) -> RuntimeRequestOutcome:
    if terminal.terminal_position is None or terminal.trace_disposition is None:
        raise RuntimeDeliveryUnknown(
            f"root response acknowledged without terminal trace: {receipt.message_id}"
        )
    return RuntimeRequestOutcome(
        request=receipt,
        response=response,
        terminal_position=terminal.terminal_position,
        trace_disposition=terminal.trace_disposition,
    )


def _request_identity(envelope: RuntimeMessageEnvelope) -> str:
    return canonical_json(
        {
            "kind": envelope.kind.value,
            "source": envelope.source,
            "target": envelope.target,
            "component_contract_id": envelope.component_contract_id,
            "action_id": envelope.action_id,
            "schema_version": envelope.schema_version,
            "idempotency_key": envelope.idempotency_key,
            "payload": envelope.payload,
        }
    )


async def _invoke_callable(
    callback: Callable[..., object], *args: object, **kwargs: object
) -> object:
    if inspect.iscoroutinefunction(callback):
        return await cast(Callable[..., Awaitable[object]], callback)(*args, **kwargs)
    thread_task = asyncio.create_task(asyncio.to_thread(callback, *args, **kwargs))
    try:
        value = await asyncio.shield(thread_task)
    except asyncio.CancelledError:
        await asyncio.shield(asyncio.gather(thread_task, return_exceptions=True))
        raise
    if inspect.isawaitable(value):
        return await cast(Awaitable[object], value)
    return value


def _request_envelope(
    action: ActionRef,
    arguments: JsonObject,
    *,
    source: RuntimeAddress,
    target: RuntimeAddress,
    message_id: UUID,
    trace_id: UUID,
    kind: RuntimeMessageKind = RuntimeMessageKind.REQUEST,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> RuntimeMessageEnvelope:
    return RuntimeMessageEnvelope(
        message_id=message_id,
        kind=kind,
        source=source,
        target=target,
        component_contract_id=action.component_contract_id,
        action_id=action.action_id,
        schema_version=action.schema_version,
        trace_id=trace_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        created_at=datetime.now(UTC).isoformat(),
        payload=RuntimePayload(
            codec_id=action.request_codec_id,
            codec_version=action.request_codec_version,
            content_type=action.request_content_type,
            value=arguments,
        ),
    )


def _complete_descriptor(binding: ActionBinding) -> RuntimeActionBindingDescriptor:
    descriptor = binding.descriptor
    failure_names = descriptor.supported_failure_names or tuple(
        failure.__name__ for failure in binding.failure_types
    )
    failure_bindings = descriptor.failure_bindings or tuple(
        RuntimeFailureBindingDescriptor(
            failure_name=name,
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
        for name in failure_names
    )
    has_effect = descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT or any(
        item.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT for item in failure_bindings
    )
    return replace(
        descriptor,
        supported_failure_names=failure_names,
        failure_bindings=failure_bindings,
        canonical_effect_schema_version=(
            descriptor.canonical_effect_schema_version or 1 if has_effect else None
        ),
        canonical_effect_codec_id=(
            descriptor.canonical_effect_codec_id
            or f"{descriptor.binding_id}.{descriptor.action_id}.effect.json"
            if has_effect
            else None
        ),
        canonical_effect_codec_version=(
            descriptor.canonical_effect_codec_version or 1 if has_effect else None
        ),
    )


def _validate_descriptor(
    descriptor: RuntimeActionBindingDescriptor, binding: ActionBinding
) -> None:
    if any(
        value < 1
        for value in (
            descriptor.binding_version,
            descriptor.schema_version,
            descriptor.request_codec_version,
            descriptor.result_codec_version,
            descriptor.failure_codec_version,
        )
    ):
        raise RuntimeBindingInvalid("binding and codec versions must be positive")
    if descriptor.deadline_seconds is not None and descriptor.deadline_seconds <= 0:
        raise RuntimeBindingInvalid("action deadline must be positive")
    if (
        descriptor.consistency_group is None
        and descriptor.consistency_access.value != "independent"
    ):
        raise RuntimeBindingInvalid("shared or exclusive access requires a consistency group")
    if descriptor.recovery_authorized and (
        descriptor.replay_mode is not RuntimeReplayMode.COORDINATOR_TRACE
        or descriptor.externally_effectful
    ):
        raise RuntimeBindingInvalid("recovery ingress must be a non-effectful coordinating action")
    if descriptor.replay_mode is RuntimeReplayMode.CANONICAL_EFFECT and (
        binding.build_replay_effect is None or binding.apply_replay_effect is None
    ):
        raise RuntimeBindingInvalid(
            f"canonical action lacks replay mapping: {descriptor.action_id}"
        )


def _failure_descriptor(
    descriptor: RuntimeActionBindingDescriptor, error: Exception
) -> RuntimeFailureBindingDescriptor | None:
    names = {failure.__name__ for failure in type(error).mro()}
    return next(
        (item for item in descriptor.failure_bindings if item.failure_name in names),
        None,
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


def _validate_effect_identity(
    effect: JsonObject, bindings: dict[str, ActionBinding]
) -> tuple[str, JsonObject]:
    try:
        action_id = str(effect["action_id"])
        payload = effect["payload"]
    except KeyError as error:
        raise RuntimePayloadInvalid(f"malformed canonical effect: {error}") from error
    binding = bindings.get(action_id)
    if binding is None:
        raise RuntimeBindingInvalid(f"canonical effect action is not registered: {action_id}")
    descriptor = binding.descriptor
    expected = {
        "binding_id": descriptor.binding_id,
        "binding_version": descriptor.binding_version,
        "component_contract_id": descriptor.component_contract_id,
        "action_id": descriptor.action_id,
        "schema_version": descriptor.schema_version,
        "effect_schema_version": descriptor.canonical_effect_schema_version,
        "effect_codec_id": descriptor.canonical_effect_codec_id,
        "effect_codec_version": descriptor.canonical_effect_codec_version,
    }
    if any(effect.get(key) != value for key, value in expected.items()):
        raise RuntimeBindingInvalid(f"canonical effect identity mismatch: {action_id}")
    if not isinstance(payload, dict):
        raise RuntimePayloadInvalid("canonical effect payload must be an object")
    return action_id, cast(JsonObject, payload)


def _effect_digest(effect: JsonObject | None) -> str | None:
    if effect is None:
        return None
    return hashlib.sha256(canonical_json(effect).encode()).hexdigest()


def _exception_evidence(error: Exception) -> JsonObject:
    evidence: JsonObject = {}
    for name in ("transaction_id", "ledger_position"):
        value = getattr(error, name, None)
        if value is not None:
            evidence[name] = encode_json(value)
    report = getattr(error, "validation_report", None)
    if report is not None:
        encoded = encode_json(report)
        if isinstance(encoded, dict):
            raw_findings = encoded.get("findings")
            findings = raw_findings if isinstance(raw_findings, list) else []
            bounded: list[JsonValue] = []
            for item in findings[:100]:
                if not isinstance(item, dict):
                    continue
                bounded.append(
                    {
                        key: value
                        for key, value in item.items()
                        if key
                        in {
                            "track",
                            "severity",
                            "code",
                            "message",
                            "suggestion",
                            "affected_references",
                        }
                    }
                )
            evidence["validation_report"] = {
                "accepted": bool(encoded.get("accepted", False)),
                "findings": bounded,
                "finding_count": len(findings),
                "truncated": len(findings) > len(bounded),
            }
    return evidence
