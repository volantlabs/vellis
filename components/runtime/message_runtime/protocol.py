from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    ComponentOccurrenceRegistration,
    JsonObject,
    JsonScalar,
    JsonValue,
    RuntimeActionBindingDescriptor,
    RuntimeActionUnknown,
    RuntimeAddress,
    RuntimeAddressUnknown,
    RuntimeArgumentDescriptor,
    RuntimeConsistencyAccess,
    RuntimeCuratedOperationDeclaration,
    RuntimeDeliveryStatus,
    RuntimeDeliveryUnknown,
    RuntimeError,
    RuntimeExternalBoundaryDisposition,
    RuntimeExternalBoundaryMode,
    RuntimeFailStopped,
    RuntimeFailureBindingDescriptor,
    RuntimeHealth,
    RuntimeHistoryPage,
    RuntimeHistoryQuery,
    RuntimeLaneDeclaration,
    RuntimeLedgerFact,
    RuntimeLedgerUnavailable,
    RuntimeMessageConflict,
    RuntimeMessageEnvelope,
    RuntimeMessageKind,
    RuntimeMessageOutcome,
    RuntimeMessageReceipt,
    RuntimeParticipant,
    RuntimeParticipantContext,
    RuntimePayload,
    RuntimePayloadDisposition,
    RuntimeQueueFull,
    RuntimeReconstructionReport,
    RuntimeReconstructionRequest,
    RuntimeRegistrationInvalid,
    RuntimeReplayIncompatible,
    RuntimeReplayMode,
    RuntimeReplayTargetNotPrepared,
    RuntimeRequestIndeterminate,
    RuntimeRequestOutcome,
    RuntimeRequestTimedOut,
    RuntimeSchemaUnsupported,
    RuntimeStorageVersionUnsupported,
    RuntimeTopologyConfirmation,
    RuntimeTopologyManifest,
    RuntimeTraceDisposition,
)


@dataclass(frozen=True, slots=True)
class RuntimeCausalTrace:
    trace_id: UUID
    facts: tuple[RuntimeLedgerFact, ...]
    disposition: RuntimeTraceDisposition | None


@dataclass(frozen=True, slots=True)
class RuntimeTraceSummary:
    trace_id: UUID
    root_message_id: UUID
    root_action_id: str
    terminal_position: int
    disposition: RuntimeTraceDisposition


@dataclass(frozen=True, slots=True)
class RuntimeTraceSummaryPage:
    summaries: tuple[RuntimeTraceSummary, ...]
    next_position: int | None = None


class MessageRuntime(Protocol):
    @property
    def health(self) -> RuntimeHealth: ...

    def address_for(self, instance_key: str) -> RuntimeAddress: ...

    async def current_position(self) -> int: ...

    async def prepare_static_topology(self, manifest: RuntimeTopologyManifest) -> None: ...

    async def register_occurrence(
        self, declaration: ComponentOccurrenceDeclaration
    ) -> ComponentOccurrenceRegistration: ...

    async def attach_participant(
        self,
        registration: ComponentOccurrenceRegistration,
        participant: RuntimeParticipant,
        actions: tuple[RuntimeActionBindingDescriptor, ...] = (),
    ) -> None: ...

    async def confirm_static_topology(
        self, manifest: RuntimeTopologyManifest
    ) -> RuntimeTopologyConfirmation: ...

    async def send(self, message: RuntimeMessageEnvelope) -> RuntimeMessageReceipt: ...

    async def query_history(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage: ...

    async def count_history(self, query: RuntimeHistoryQuery) -> int: ...

    async def query_trace_summaries(
        self,
        *,
        after_position: int | None = None,
        limit: int = 100,
        newest_first: bool = False,
        root_action_ids: tuple[str, ...] = (),
    ) -> RuntimeTraceSummaryPage: ...

    async def get_trace(
        self, trace_id: UUID, *, include_payload: bool = False
    ) -> RuntimeCausalTrace: ...

    async def get_envelope(self, message_id: UUID) -> RuntimeMessageEnvelope | None: ...

    async def lookup_message_outcome(
        self, message_id: UUID
    ) -> RuntimeMessageOutcome | None: ...

    async def reconstruct(
        self, request: RuntimeReconstructionRequest
    ) -> RuntimeReconstructionReport: ...

    async def record_branch_provenance(
        self,
        *,
        source_runtime_id: UUID,
        source_cursor: int,
        verified_digest: str,
    ) -> int: ...

    async def aclose(self) -> None: ...


__all__ = [
    "ComponentOccurrenceDeclaration",
    "ComponentOccurrenceRegistration",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "MessageRuntime",
    "RuntimeActionBindingDescriptor",
    "RuntimeActionUnknown",
    "RuntimeAddress",
    "RuntimeAddressUnknown",
    "RuntimeArgumentDescriptor",
    "RuntimeCausalTrace",
    "RuntimeConsistencyAccess",
    "RuntimeCuratedOperationDeclaration",
    "RuntimeDeliveryStatus",
    "RuntimeDeliveryUnknown",
    "RuntimeError",
    "RuntimeExternalBoundaryDisposition",
    "RuntimeExternalBoundaryMode",
    "RuntimeFailStopped",
    "RuntimeFailureBindingDescriptor",
    "RuntimeHistoryPage",
    "RuntimeHistoryQuery",
    "RuntimeHealth",
    "RuntimeLaneDeclaration",
    "RuntimeLedgerFact",
    "RuntimeLedgerUnavailable",
    "RuntimeMessageConflict",
    "RuntimeMessageEnvelope",
    "RuntimeMessageKind",
    "RuntimeMessageOutcome",
    "RuntimeMessageReceipt",
    "RuntimeParticipant",
    "RuntimeParticipantContext",
    "RuntimePayload",
    "RuntimePayloadDisposition",
    "RuntimeQueueFull",
    "RuntimeReconstructionReport",
    "RuntimeReconstructionRequest",
    "RuntimeRegistrationInvalid",
    "RuntimeReplayIncompatible",
    "RuntimeReplayMode",
    "RuntimeReplayTargetNotPrepared",
    "RuntimeRequestOutcome",
    "RuntimeRequestIndeterminate",
    "RuntimeRequestTimedOut",
    "RuntimeSchemaUnsupported",
    "RuntimeStorageVersionUnsupported",
    "RuntimeTopologyConfirmation",
    "RuntimeTopologyManifest",
    "RuntimeTraceDisposition",
    "RuntimeTraceSummary",
    "RuntimeTraceSummaryPage",
]
