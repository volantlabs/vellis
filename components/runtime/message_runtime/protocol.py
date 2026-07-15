from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class RuntimeMessageKind(StrEnum):
    REQUEST = "request"
    RESPONSE = "response"
    FAULT = "fault"
    SIGNAL = "signal"


class RuntimeTraceDisposition(StrEnum):
    COMMITTED = "committed"
    ABORTED = "aborted"
    INDETERMINATE = "indeterminate"


class RuntimeDeliveryStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    FAULTED = "faulted"
    TIMED_OUT = "timed_out"


class RuntimeReplayMode(StrEnum):
    NO_STATE_EFFECT = "no_state_effect"
    CANONICAL_EFFECT = "canonical_effect"
    COORDINATOR_TRACE = "coordinator_trace"
    EXTERNAL_EXCHANGE = "external_exchange"


class RuntimeExternalBoundaryMode(StrEnum):
    PLAYBACK_ONLY = "playback_only"
    LIVE = "live"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RuntimeAddress:
    runtime_id: UUID
    instance_id: UUID


@dataclass(frozen=True, slots=True)
class RuntimePayload:
    codec_id: str
    codec_version: int
    value: JsonValue
    content_type: str = "application/json"


@dataclass(frozen=True, slots=True)
class RuntimeMessageEnvelope:
    message_id: UUID
    kind: RuntimeMessageKind
    source: RuntimeAddress
    target: RuntimeAddress
    component_contract_id: str
    action_id: str
    schema_version: int
    trace_id: UUID
    created_at: str
    payload: RuntimePayload
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ComponentOccurrenceDeclaration:
    """Static occurrence contract before the runtime assigns its incarnation UUID."""

    instance_key: str
    component_contract_id: str
    binding_id: str
    binding_version: int
    queue_capacity: int = 128
    max_in_flight: int = 1
    replay_authority: RuntimeReplayMode = RuntimeReplayMode.NO_STATE_EFFECT
    configuration_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComponentOccurrenceRegistration:
    instance_key: str
    instance_id: UUID
    component_contract_id: str
    binding_id: str
    binding_version: int
    queue_capacity: int = 128
    max_in_flight: int = 1
    replay_authority: RuntimeReplayMode = RuntimeReplayMode.NO_STATE_EFFECT
    configuration_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeCuratedOperationDeclaration:
    operation_id: str
    target_instance_key: str
    component_contract_id: str
    action_id: str
    schema_version: int


@dataclass(frozen=True, slots=True)
class RuntimeTopologyManifest:
    runtime_key: str
    manifest_schema_version: int
    occurrences: tuple[ComponentOccurrenceDeclaration, ...]
    curated_operations: tuple[RuntimeCuratedOperationDeclaration, ...]
    manifest_hash: str


@dataclass(frozen=True, slots=True)
class RuntimeTopologyConfirmation:
    manifest_hash: str
    topology_hash: str
    occurrence_count: int


@dataclass(frozen=True, slots=True)
class RuntimeMessageReceipt:
    message_id: UUID
    trace_id: UUID
    accepted_position: int
    status: RuntimeDeliveryStatus


@dataclass(frozen=True, slots=True)
class RuntimeRequestOutcome:
    request: RuntimeMessageReceipt
    response: RuntimeMessageEnvelope
    terminal_position: int
    trace_disposition: RuntimeTraceDisposition


@dataclass(frozen=True, slots=True)
class RuntimeHistoryQuery:
    after_position: int | None = None
    through_position: int | None = None
    after_time: str | None = None
    through_time: str | None = None
    runtime_id: UUID | None = None
    instance_key: str | None = None
    instance_id: UUID | None = None
    component_contract_id: str | None = None
    message_id: UUID | None = None
    trace_id: UUID | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    action_id: str | None = None
    message_kind: RuntimeMessageKind | None = None
    schema_version: int | None = None
    delivery_status: RuntimeDeliveryStatus | None = None
    trace_disposition: RuntimeTraceDisposition | None = None
    fact_type: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class RuntimeLedgerFact:
    runtime_position: int
    fact_type: str
    recorded_at: str
    runtime_id: UUID
    details: JsonObject = field(default_factory=dict)
    instance_key: str | None = None
    instance_id: UUID | None = None
    component_contract_id: str | None = None
    message_id: UUID | None = None
    trace_id: UUID | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    action_id: str | None = None
    schema_version: int | None = None
    envelope: RuntimeMessageEnvelope | None = None


@dataclass(frozen=True, slots=True)
class RuntimeHistoryPage:
    facts: tuple[RuntimeLedgerFact, ...]
    next_position: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeCausalTrace:
    trace_id: UUID
    facts: tuple[RuntimeLedgerFact, ...]
    disposition: RuntimeTraceDisposition | None


@dataclass(frozen=True, slots=True)
class RuntimeExternalBoundaryDisposition:
    boundary_id: str
    mode: RuntimeExternalBoundaryMode
    limitation: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeReconstructionRequest:
    through_position: int | None = None
    source_runtime_id: UUID | None = None
    checkpoint_reference: str | None = None
    checkpoint_references: JsonObject = field(default_factory=dict)
    reset_targets: bool = False
    external_boundaries: tuple[RuntimeExternalBoundaryDisposition, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeReconstructionReport:
    start_position: int
    through_position: int
    applied_effects: int
    skipped_effects: int
    incompatible_effects: int
    state_digests: JsonObject = field(default_factory=dict)
    verified: bool = False
    external_effects_skipped: int = 0
    external_boundaries: tuple[RuntimeExternalBoundaryDisposition, ...] = ()
    limitations: tuple[str, ...] = ()
    verified_digest: str | None = None


class RuntimeError(Exception):
    """Base failure for the message runtime."""


class RuntimeRegistrationInvalid(RuntimeError):
    """A component occurrence registration is invalid or conflicts with durable identity."""


class RuntimeAddressUnknown(RuntimeError):
    """A runtime or component occurrence address is not registered."""


class RuntimeActionUnknown(RuntimeError):
    """The target binding does not expose the requested action."""


class RuntimeSchemaUnsupported(RuntimeError):
    """The requested message schema is unsupported by the target binding."""


class RuntimeMessageConflict(RuntimeError):
    """A message ID was reused with different immutable content."""


class RuntimeQueueFull(RuntimeError):
    """The target occurrence queue has reached its configured bound."""


class RuntimeLedgerUnavailable(RuntimeError):
    """The runtime ledger could not durably record a required fact."""


class RuntimeFailStopped(RuntimeError):
    """The runtime rejected traffic after an unconfirmed terminal effect."""


class RuntimeRequestTimedOut(RuntimeError):
    """The caller wait elapsed without cancelling the handler."""

    def __init__(self, message_id: UUID) -> None:
        self.message_id = message_id
        super().__init__(f"request wait timed out; query outcome by message_id={message_id}")


class RuntimeReplayIncompatible(RuntimeError):
    """Recorded effects cannot be applied by the attached binding version."""


class RuntimeReplayTargetNotPrepared(RuntimeReplayIncompatible):
    """A reconstruction target is non-empty or lacks the required state SPI."""


class MessageRuntime(Protocol):
    async def prepare_static_topology(
        self,
        manifest: RuntimeTopologyManifest,
    ) -> None:
        """Durably reserve one complete static topology before provisioning it."""
        ...

    async def register_occurrence(
        self, declaration: ComponentOccurrenceDeclaration
    ) -> ComponentOccurrenceRegistration:
        """Allocate or resolve and persist one runtime-owned occurrence identity."""
        ...

    async def send(self, message: RuntimeMessageEnvelope) -> RuntimeMessageReceipt:
        """Durably accept a request or signal before dispatch."""
        ...

    async def confirm_static_topology(
        self,
        manifest: RuntimeTopologyManifest,
    ) -> RuntimeTopologyConfirmation:
        """Confirm complete occurrence contracts before exposing traffic."""
        ...

    async def request(
        self,
        message: RuntimeMessageEnvelope,
        timeout_seconds: float | None = None,
    ) -> RuntimeRequestOutcome:
        """Durably accept and await a request without cancellation-on-timeout."""
        ...

    async def query_history(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage:
        """Read immutable runtime facts with cursor pagination."""
        ...

    async def get_trace(self, trace_id: UUID) -> RuntimeCausalTrace:
        """Return one complete causal trace and its confirmed disposition."""
        ...

    async def reconstruct(
        self, request: RuntimeReconstructionRequest
    ) -> RuntimeReconstructionReport:
        """Apply committed canonical effects through a selected cursor."""
        ...

    async def record_branch_provenance(
        self,
        *,
        source_runtime_id: UUID,
        source_cursor: int,
        verified_digest: str,
    ) -> int:
        """Durably authorize ingress after verified historical reconstruction."""
        ...
