from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from components.runtime.message_runtime.protocol import (
    JsonObject,
    RuntimeMessageEnvelope,
    RuntimeReplayMode,
    RuntimeTraceDisposition,
)


class RuntimeActionIdempotency(StrEnum):
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"
    UNSPECIFIED = "unspecified"


@dataclass(frozen=True, slots=True)
class RuntimeArgumentDescriptor:
    """One declared request argument and its public default, when any."""

    name: str
    required: bool
    default: object | None = None


@dataclass(frozen=True, slots=True)
class RuntimeFailureBindingDescriptor:
    failure_name: str
    codec_id: str
    codec_version: int
    content_type: str
    trace_disposition: RuntimeTraceDisposition
    replay_mode: RuntimeReplayMode = RuntimeReplayMode.NO_STATE_EFFECT


@dataclass(frozen=True, slots=True)
class RuntimeActionBindingDescriptor:
    component_contract_id: str
    action_id: str
    binding_id: str
    binding_version: int
    schema_version: int
    request_codec_id: str
    result_codec_id: str
    failure_codec_id: str
    idempotency: RuntimeActionIdempotency
    replay_mode: RuntimeReplayMode
    concurrency_lane: str = "serialized"
    externally_effectful: bool = False
    request_content_type: str = "application/json"
    request_codec_version: int = 1
    result_content_type: str = "application/json"
    result_codec_version: int = 1
    failure_content_type: str = "application/json"
    failure_codec_version: int = 1
    request_arguments: tuple[RuntimeArgumentDescriptor, ...] = ()
    supported_failure_names: tuple[str, ...] = ()
    failure_bindings: tuple[RuntimeFailureBindingDescriptor, ...] = ()
    canonical_effect_schema_version: int | None = None
    canonical_effect_codec_id: str | None = None
    canonical_effect_codec_version: int | None = None
    modeled_fault_trace_disposition: RuntimeTraceDisposition = RuntimeTraceDisposition.ABORTED
    max_in_flight: int = 1
    recovery_authorized: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeDispatchResult:
    response: RuntimeMessageEnvelope
    trace_disposition: RuntimeTraceDisposition
    canonical_effect: JsonObject | None = None
    effect_digest: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeBindingDescription:
    binding_id: str
    binding_version: int
    actions: tuple[RuntimeActionBindingDescriptor, ...]


class RuntimeBindingInvalid(Exception):
    """A binding descriptor or target component is invalid."""


class RuntimePayloadInvalid(Exception):
    """A request or replay payload cannot be decoded by its declared codec."""


class RuntimeTerminalEncodingFailed(Exception):
    """A terminal response or replay effect could not be encoded after invocation."""


class RuntimeComponentFault(Exception):
    """A modeled component failure encoded at the adapter boundary."""

    def __init__(self, fault_type: str, message: str, evidence: JsonObject | None = None) -> None:
        self.fault_type = fault_type
        self.evidence = evidence or {}
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RuntimeReplayStateStatus:
    available: bool
    empty: bool
    prepared: bool = False
    checkpoint_cursor: int = 0
    state_digest: str | None = None
    limitations: tuple[str, ...] = ()


class ComponentRuntimeAdapter(Protocol):
    def describe(self) -> RuntimeBindingDescription:
        """Return the explicit action and codec inventory."""
        ...

    async def dispatch(self, request: RuntimeMessageEnvelope) -> RuntimeDispatchResult:
        """Invoke exactly one registered component action."""
        ...

    async def apply_replay_effect(self, effect: JsonObject) -> None:
        """Apply one compatible committed canonical effect."""
        ...

    async def replay_state_status(self) -> RuntimeReplayStateStatus:
        """Report whether the adapter host can safely receive reconstruction effects."""
        ...

    async def reset_replay_state(self) -> None:
        """Reset owned state to the binding's declared empty state."""
        ...

    async def import_replay_checkpoint(self, reference: str) -> int:
        """Import a compatible checkpoint and return its represented runtime cursor."""
        ...

    async def replay_state_digest(self) -> str:
        """Return a deterministic digest of canonical component state."""
        ...

    async def verify_replay_state(self) -> tuple[str, ...]:
        """Return invariant or reconstruction limitations; empty means verified."""
        ...
