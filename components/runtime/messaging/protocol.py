from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = Any
type JsonObject = dict[str, Any]


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
    INDETERMINATE = "indeterminate"


class RuntimeHealth(StrEnum):
    STARTING = "starting"
    READY = "ready"
    QUIESCING = "quiescing"
    RECONSTRUCTING = "reconstructing"
    RECOVERY_REQUIRED = "recovery_required"
    BRANCH_PENDING = "branch_pending"
    FAIL_STOPPED = "fail_stopped"
    CLOSING = "closing"
    CLOSED = "closed"


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


class RuntimeActionIdempotency(StrEnum):
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"
    UNSPECIFIED = "unspecified"


class RuntimeConsistencyAccess(StrEnum):
    INDEPENDENT = "independent"
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


class RuntimePayloadDisposition(StrEnum):
    """Contract-level purpose of an action payload, independent of component role."""

    COMMAND = "command"
    QUERY_RESULT = "query_result"
    DIAGNOSTIC = "diagnostic"
    CANONICAL_DELTA = "canonical_delta"
    STATE_TRANSFER = "state_transfer"
    EXTERNAL_DOCUMENT = "external_document"


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
class RuntimeLaneDeclaration:
    name: str
    queue_capacity: int = 128
    worker_limit: int = 1


@dataclass(frozen=True, slots=True)
class ComponentOccurrenceDeclaration:
    instance_key: str
    component_contract_id: str
    binding_id: str
    binding_version: int
    lanes: tuple[RuntimeLaneDeclaration, ...] = (RuntimeLaneDeclaration("serialized"),)
    replay_authority: RuntimeReplayMode = RuntimeReplayMode.NO_STATE_EFFECT
    configuration_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComponentOccurrenceRegistration:
    instance_key: str
    instance_id: UUID
    component_contract_id: str
    binding_id: str
    binding_version: int
    lanes: tuple[RuntimeLaneDeclaration, ...]
    replay_authority: RuntimeReplayMode
    configuration_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeCuratedOperationDeclaration:
    operation_id: str
    target_instance_key: str
    component_contract_id: str
    action_id: str
    schema_version: int
    binding_id: str
    binding_version: int
    request_codec_id: str
    request_codec_version: int
    request_payload_disposition: RuntimePayloadDisposition
    result_payload_disposition: RuntimePayloadDisposition
    fault_payload_disposition: RuntimePayloadDisposition
    effect_payload_disposition: RuntimePayloadDisposition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeTopologyManifest:
    runtime_key: str
    manifest_schema_version: int
    occurrences: tuple[ComponentOccurrenceDeclaration, ...]
    curated_operations: tuple[RuntimeCuratedOperationDeclaration, ...]
    manifest_hash: str
    curated_registration_digest: str | None = None


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
    terminal_position: int | None = None
    trace_disposition: RuntimeTraceDisposition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeRequestOutcome:
    request: RuntimeMessageReceipt
    response: RuntimeMessageEnvelope
    terminal_position: int
    trace_disposition: RuntimeTraceDisposition


@dataclass(frozen=True, slots=True)
class RuntimeMessageOutcome:
    request_envelope: RuntimeMessageEnvelope
    request_receipt: RuntimeMessageReceipt
    terminal_envelope: RuntimeMessageEnvelope | None = None
    terminal_receipt: RuntimeMessageReceipt | None = None


@dataclass(frozen=True, slots=True)
class RuntimeCanonicalEffectReference:
    """Immutable reference to one recorded descendant effect."""

    request_message_id: UUID
    effect_digest: str


@dataclass(frozen=True, slots=True)
class RuntimeArgumentDescriptor:
    name: str
    required: bool
    default: object | None = None
    schema: JsonObject = field(default_factory=dict)


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
    consistency_group: str | None = None
    consistency_access: RuntimeConsistencyAccess = RuntimeConsistencyAccess.INDEPENDENT
    deadline_seconds: float | None = None
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
    recovery_authorized: bool = False
    request_payload_disposition: RuntimePayloadDisposition = RuntimePayloadDisposition.COMMAND
    result_payload_disposition: RuntimePayloadDisposition = RuntimePayloadDisposition.QUERY_RESULT
    fault_payload_disposition: RuntimePayloadDisposition = RuntimePayloadDisposition.DIAGNOSTIC
    effect_payload_disposition: RuntimePayloadDisposition | None = None
    request_schema: JsonObject = field(default_factory=dict)
    result_schema: JsonObject = field(default_factory=dict)
    fault_schema: JsonObject = field(default_factory=dict)

    def action_ref(self) -> ActionRef:
        return ActionRef(
            component_contract_id=self.component_contract_id,
            action_id=self.action_id,
            schema_version=self.schema_version,
            request_codec_id=self.request_codec_id,
            request_codec_version=self.request_codec_version,
            request_content_type=self.request_content_type,
        )


@dataclass(frozen=True, slots=True)
class ActionRef:
    component_contract_id: str
    action_id: str
    schema_version: int
    request_codec_id: str
    request_codec_version: int = 1
    request_content_type: str = "application/json"


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
    include_payload: bool = False


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
    """Base failure shared by runtime and participation implementations."""


class RuntimeRegistrationInvalid(RuntimeError):
    """A topology declaration or attachment is invalid."""


class RuntimeAddressUnknown(RuntimeError):
    """A runtime or component occurrence address is not registered."""


class RuntimeActionUnknown(RuntimeError):
    """The target participation kit does not expose the requested action."""


class RuntimeSchemaUnsupported(RuntimeError):
    """A message schema or codec is unsupported by its target action."""


class RuntimeLedgerUnavailable(RuntimeError):
    """The runtime could not durably record a required fact."""


class RuntimeFailStopped(RuntimeError):
    """The runtime rejected traffic after an unconfirmed terminal effect."""


class RuntimeRequestTimedOut(RuntimeError):
    """An edge caller stopped waiting without cancelling component execution."""

    def __init__(self, message_id: UUID) -> None:
        self.message_id = message_id
        super().__init__(f"request wait timed out; query outcome by message_id={message_id}")


class RuntimeRequestIndeterminate(RuntimeError):
    """A durable request has no usable terminal result and requires recovery."""

    def __init__(self, message_id: UUID) -> None:
        self.message_id = message_id
        super().__init__(f"request outcome is indeterminate; message_id={message_id}")


class RuntimeReplayIncompatible(RuntimeError):
    """Recorded effects cannot be applied by attached participation kits."""


class RuntimeReplayTargetNotPrepared(RuntimeReplayIncompatible):
    """A reconstruction target is non-empty or cannot receive replay effects."""


class RuntimeDeliveryUnknown(RuntimeError):
    """A participant attempted an unknown, duplicate, or wrong-kind completion."""


class RuntimeMessageConflict(RuntimeError):
    """A message identity was reused with different immutable content."""


class RuntimeQueueFull(RuntimeError):
    """A declared action lane has reached its configured capacity."""


class RuntimeStorageVersionUnsupported(RuntimeError):
    """The data root belongs to an incompatible runtime storage generation."""


class RuntimeParticipantContext(Protocol):
    async def send(
        self,
        action: ActionRef,
        arguments: JsonObject,
        *,
        target: RuntimeAddress,
        kind: RuntimeMessageKind = RuntimeMessageKind.REQUEST,
        message_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> RuntimeMessageReceipt: ...

    async def complete(
        self,
        request_message_id: UUID,
        result: RuntimePayload,
        *,
        trace_disposition: RuntimeTraceDisposition = RuntimeTraceDisposition.COMMITTED,
        canonical_effect: JsonObject | None = None,
        effect_digest: str | None = None,
    ) -> RuntimeMessageReceipt: ...

    async def fault(
        self,
        request_message_id: UUID,
        error: RuntimePayload,
        *,
        trace_disposition: RuntimeTraceDisposition,
        canonical_effect: JsonObject | None = None,
        effect_digest: str | None = None,
    ) -> RuntimeMessageReceipt: ...

    async def ack(
        self,
        message_id: UUID,
        *,
        canonical_effect: JsonObject | None = None,
        effect_digest: str | None = None,
    ) -> RuntimeMessageReceipt: ...

    async def canonical_effect_reference(
        self, request_message_id: UUID
    ) -> RuntimeCanonicalEffectReference: ...

    def address_for(self, instance_key: str) -> RuntimeAddress: ...


class RuntimeParticipant(Protocol):
    async def deliver(
        self,
        envelope: RuntimeMessageEnvelope,
        context: RuntimeParticipantContext,
    ) -> None: ...
