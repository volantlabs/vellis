from typing import TYPE_CHECKING, Any

from components.runtime.message_runtime.protocol import (
    ComponentOccurrenceDeclaration,
    ComponentOccurrenceRegistration,
    JsonObject,
    JsonValue,
    MessageRuntime,
    RuntimeActionUnknown,
    RuntimeAddress,
    RuntimeAddressUnknown,
    RuntimeCausalTrace,
    RuntimeCuratedOperationDeclaration,
    RuntimeDeliveryStatus,
    RuntimeError,
    RuntimeExternalBoundaryDisposition,
    RuntimeExternalBoundaryMode,
    RuntimeFailStopped,
    RuntimeHistoryPage,
    RuntimeHistoryQuery,
    RuntimeLedgerFact,
    RuntimeLedgerUnavailable,
    RuntimeMessageConflict,
    RuntimeMessageEnvelope,
    RuntimeMessageKind,
    RuntimeMessageReceipt,
    RuntimePayload,
    RuntimeQueueFull,
    RuntimeReconstructionReport,
    RuntimeReconstructionRequest,
    RuntimeRegistrationInvalid,
    RuntimeReplayIncompatible,
    RuntimeReplayMode,
    RuntimeReplayTargetNotPrepared,
    RuntimeRequestOutcome,
    RuntimeRequestTimedOut,
    RuntimeSchemaUnsupported,
    RuntimeTopologyConfirmation,
    RuntimeTopologyManifest,
    RuntimeTraceDisposition,
)

if TYPE_CHECKING:
    from components.runtime.message_runtime.implementation import SqliteMessageRuntime


def __getattr__(name: str) -> Any:
    if name == "SqliteMessageRuntime":
        from components.runtime.message_runtime.implementation import SqliteMessageRuntime

        return SqliteMessageRuntime
    raise AttributeError(name)


__all__ = [
    "ComponentOccurrenceDeclaration",
    "ComponentOccurrenceRegistration",
    "JsonObject",
    "JsonValue",
    "MessageRuntime",
    "RuntimeActionUnknown",
    "RuntimeAddress",
    "RuntimeAddressUnknown",
    "RuntimeCausalTrace",
    "RuntimeCuratedOperationDeclaration",
    "RuntimeDeliveryStatus",
    "RuntimeError",
    "RuntimeExternalBoundaryDisposition",
    "RuntimeExternalBoundaryMode",
    "RuntimeFailStopped",
    "RuntimeHistoryPage",
    "RuntimeHistoryQuery",
    "RuntimeLedgerFact",
    "RuntimeLedgerUnavailable",
    "RuntimeMessageConflict",
    "RuntimeMessageEnvelope",
    "RuntimeMessageKind",
    "RuntimeMessageReceipt",
    "RuntimePayload",
    "RuntimeQueueFull",
    "RuntimeReconstructionReport",
    "RuntimeReconstructionRequest",
    "RuntimeRegistrationInvalid",
    "RuntimeReplayIncompatible",
    "RuntimeReplayTargetNotPrepared",
    "RuntimeReplayMode",
    "RuntimeRequestOutcome",
    "RuntimeRequestTimedOut",
    "RuntimeSchemaUnsupported",
    "RuntimeTraceDisposition",
    "RuntimeTopologyConfirmation",
    "RuntimeTopologyManifest",
    "SqliteMessageRuntime",
]
