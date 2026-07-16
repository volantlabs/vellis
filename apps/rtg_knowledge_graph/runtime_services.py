from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

from apps.rtg_knowledge_graph.mcp_toolset import TOOL_NAMES
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import (
    JsonObject,
    RuntimeAddress,
    RuntimeCausalTrace,
    RuntimeHealth,
    RuntimeHistoryPage,
    RuntimeHistoryQuery,
    RuntimeLedgerFact,
    RuntimeMessageEnvelope,
    RuntimeMessageKind,
    RuntimeMessageOutcome,
    RuntimeReconstructionReport,
    RuntimeReconstructionRequest,
    RuntimeTraceSummaryPage,
)
from components.runtime.messaging import canonical_json

_MIGRATION_ACTIONS = {
    "application.vellis.facade.rtg_stage_knowledge_changes": "knowledge_staged",
    "application.vellis.facade.rtg_apply_migration_cutover": "cutover_requested",
    "application.vellis.facade.rtg_abandon_migration": "migration_abandoned",
}
_REQUEST_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class VellisRuntime(Protocol):
    """Minimal trusted runtime surface consumed by Vellis history services."""

    @property
    def runtime_id(self) -> UUID: ...

    @property
    def runtime_key(self) -> str: ...

    @property
    def health(self) -> RuntimeHealth: ...

    async def current_position(self) -> int: ...

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

    async def get_trace(self, trace_id: UUID) -> RuntimeCausalTrace: ...

    async def get_envelope(self, message_id: UUID) -> RuntimeMessageEnvelope | None: ...

    async def lookup_message_outcome(
        self, message_id: UUID
    ) -> RuntimeMessageOutcome | None: ...

    def address_for(self, instance_key: str) -> RuntimeAddress: ...

    async def reconstruct(
        self,
        request: RuntimeReconstructionRequest,
    ) -> RuntimeReconstructionReport: ...


@dataclass(slots=True)
class VellisRuntimeServices:
    """Trusted Vellis projection over runtime history, health, and reconstruction."""

    runtime: VellisRuntime
    startup_reconstruction: RuntimeReconstructionReport | None = None

    async def status(self) -> JsonObject:
        message_count = await self.runtime.count_history(
            RuntimeHistoryQuery(fact_type="message_accepted")
        )
        latest_page = await self.runtime.query_trace_summaries(limit=1, newest_first=True)
        latest = latest_page.summaries[0] if latest_page.summaries else None
        current_position = await self.runtime.current_position()
        return {
            "runtime_id": str(self.runtime.runtime_id),
            "runtime_key": self.runtime.runtime_key,
            "health": self.runtime.health.value,
            "current_position": current_position,
            "message_count": message_count,
            "last_trace_id": str(latest.trace_id) if latest else None,
            "last_trace_position": latest.terminal_position if latest else None,
            "last_trace_disposition": latest.disposition.value if latest else None,
        }

    async def reconstruct(self, request: RuntimeReconstructionRequest) -> JsonObject:
        report = await self.runtime.reconstruct(request)
        self.startup_reconstruction = report
        return cast(JsonObject, encode_json(report))

    async def verify_reconstruction(self, request: RuntimeReconstructionRequest) -> JsonObject:
        requested_cursor = request.through_position
        report = self.startup_reconstruction
        if report is None:
            return {
                "status": "isolated_reconstruction_required",
                "verified": False,
                "through_runtime_position": requested_cursor,
                "details": {
                    "reason": (
                        "No startup reconstruction report is available. Attach this data root "
                        "to an isolated empty composition and use the trusted runtime "
                        "reconstruction API."
                    )
                },
            }
        exact_cursor = requested_cursor in {None, report.through_position}
        return {
            "status": "reconstruction_verified"
            if report.verified and exact_cursor
            else ("isolated_reconstruction_required"),
            "verified": bool(report.verified and exact_cursor),
            "through_runtime_position": report.through_position,
            "requested_through_runtime_position": requested_cursor,
            "report": cast(JsonObject, encode_json(report)),
            "details": {
                "scope": "latest startup reconstruction",
                "historical_verification": (
                    "Copy the data root and reconstruct the isolated copy through the requested "
                    "cursor; live in-place rewind is not supported."
                ),
            },
        }

    async def migration_history(
        self,
        *,
        after_runtime_position: int | None = None,
        limit: int = 100,
    ) -> JsonObject:
        page = await self.runtime.query_trace_summaries(
            after_position=after_runtime_position,
            limit=limit,
            root_action_ids=tuple(_MIGRATION_ACTIONS),
        )
        events: list[dict[str, Any]] = []
        for summary in page.summaries:
            event_type = _MIGRATION_ACTIONS[summary.root_action_id]
            envelope = await self.runtime.get_envelope(summary.root_message_id)
            arguments = (
                cast(JsonObject, envelope.payload.value)
                if envelope is not None and isinstance(envelope.payload.value, dict)
                else {}
            )
            migration_id = _migration_id(summary.root_action_id, arguments)
            events.append(
                {
                    "event_type": event_type,
                    "runtime_position": summary.terminal_position,
                    "trace_id": str(summary.trace_id),
                    "disposition": summary.disposition.value,
                    "migration_id": migration_id,
                    "summary": _migration_event_summary(event_type, migration_id),
                }
            )
        return cast(
            JsonObject,
            encode_json(
                {
                    "events": events,
                    "source": "runtime_ledger",
                    "next_runtime_position": page.next_position,
                    "through_runtime_position": await self.runtime.current_position(),
                }
            ),
        )

    async def operation_outcome(
        self,
        *,
        message_id: str | None,
        request_key: str | None,
        include_state_transfer: bool = False,
    ) -> JsonObject:
        if (message_id is None) == (request_key is None):
            raise ValueError("provide exactly one of message_id or request_key")
        if request_key is not None:
            if _REQUEST_KEY.fullmatch(request_key) is None:
                raise ValueError(
                    "request_key must be 1-128 characters and use letters, digits, "
                    "'.', '_', ':', or '-'"
                )
            gateway = self.runtime.address_for("vellis.interface.mcp")
            resolved_id = uuid5(gateway.instance_id, request_key)
        else:
            resolved_id = UUID(str(message_id))
        outcome = await self.runtime.lookup_message_outcome(resolved_id)
        if outcome is None:
            return {
                "status": "unknown",
                "message_id": str(resolved_id),
                "guidance": "Verify the request key or message ID before retrying the operation.",
            }
        request = outcome.request_envelope
        gateway = self.runtime.address_for("vellis.interface.mcp")
        facade = self.runtime.address_for("vellis.facade.primary")
        curated_actions = {f"application.vellis.facade.{name}" for name in TOOL_NAMES}
        if (
            request.kind is not RuntimeMessageKind.REQUEST
            or request.causation_id is not None
            or request.source != gateway
            or request.target != facade
            or request.action_id not in curated_actions
        ):
            raise ValueError("operation outcome is not a curated MCP root request")
        terminal = outcome.terminal_envelope
        terminal_receipt = outcome.terminal_receipt
        result: JsonObject = {
            "status": "pending" if terminal is None else terminal.kind.value,
            "message_id": str(resolved_id),
            "trace_id": str(outcome.request_receipt.trace_id),
            "accepted_position": outcome.request_receipt.accepted_position,
            "terminal_position": (
                terminal_receipt.terminal_position if terminal_receipt is not None else None
            ),
            "disposition": (
                terminal_receipt.trace_disposition.value
                if terminal_receipt is not None
                and terminal_receipt.trace_disposition is not None
                else None
            ),
            "guidance": (
                "The operation is still executing; observe this same identity again without "
                "submitting the mutation again."
                if terminal is None
                else "This is the durable terminal outcome; do not resubmit the mutation."
            ),
        }
        if terminal is not None:
            encoded = cast(JsonObject, encode_json(terminal.payload.value))
            state_transfer = request.action_id in {
                "application.vellis.facade.rtg_export_system_snapshot",
                "application.vellis.facade.rtg_load_persisted_snapshot",
            }
            if state_transfer and not include_state_transfer:
                canonical = canonical_json(encoded).encode()
                result.update(
                    {
                        "payload_withheld": True,
                        "payload_digest": hashlib.sha256(canonical).hexdigest(),
                        "encoded_size_bytes": len(canonical),
                    }
                )
            else:
                result["outcome"] = encoded
        return result

    async def _facts(self, query: RuntimeHistoryQuery) -> tuple[RuntimeLedgerFact, ...]:
        facts: list[RuntimeLedgerFact] = []
        after = query.after_position
        while True:
            page = await self.runtime.query_history(
                RuntimeHistoryQuery(
                    after_position=after,
                    through_position=query.through_position,
                    after_time=query.after_time,
                    through_time=query.through_time,
                    runtime_id=query.runtime_id,
                    instance_key=query.instance_key,
                    instance_id=query.instance_id,
                    component_contract_id=query.component_contract_id,
                    message_id=query.message_id,
                    trace_id=query.trace_id,
                    correlation_id=query.correlation_id,
                    causation_id=query.causation_id,
                    action_id=query.action_id,
                    message_kind=query.message_kind,
                    schema_version=query.schema_version,
                    delivery_status=query.delivery_status,
                    trace_disposition=query.trace_disposition,
                    fact_type=query.fact_type,
                    limit=query.limit,
                )
            )
            facts.extend(page.facts)
            if page.next_position is None:
                return tuple(facts)
            after = page.next_position


def _migration_id(action_id: str, arguments: JsonObject) -> str | None:
    if action_id.endswith(("apply_migration_cutover", "abandon_migration")):
        value = arguments.get("migration_id")
        return str(value) if value is not None else None
    batch = arguments.get("knowledge_changes")
    if not isinstance(batch, dict):
        return None
    migration_changes = batch.get("migration_changes")
    if not isinstance(migration_changes, dict):
        return None
    writes = migration_changes.get("migration_writes")
    if not isinstance(writes, list) or not writes or not isinstance(writes[0], dict):
        return None
    migration = writes[0].get("migration")
    if not isinstance(migration, dict):
        return None
    value = migration.get("migration_id")
    return str(value) if value is not None else None


def _migration_event_summary(event_type: str, migration_id: str | None) -> str:
    subject = f"migration {migration_id}" if migration_id else "migration operation"
    return {
        "knowledge_staged": f"Staged knowledge for {subject}.",
        "cutover_requested": f"Requested cutover for {subject}.",
        "migration_abandoned": f"Abandoned {subject}.",
    }.get(event_type, subject)
