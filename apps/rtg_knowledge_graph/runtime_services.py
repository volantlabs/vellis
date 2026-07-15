from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import (
    JsonObject,
    RuntimeCausalTrace,
    RuntimeHistoryPage,
    RuntimeHistoryQuery,
    RuntimeLedgerFact,
    RuntimeReconstructionReport,
    RuntimeReconstructionRequest,
    RuntimeTraceDisposition,
)

_MIGRATION_ACTIONS = {
    "component.rtg.controller.stage_knowledge_changes": "knowledge_staged",
    "component.rtg.controller.apply_migration_cutover": "cutover_requested",
    "component.rtg.controller.abandon_migration": "migration_abandoned",
}


class VellisRuntime(Protocol):
    """Minimal trusted runtime surface consumed by Vellis history services."""

    @property
    def runtime_id(self) -> UUID: ...

    @property
    def runtime_key(self) -> str: ...

    @property
    def health(self) -> str: ...

    @property
    def current_position(self) -> int: ...

    def query_history_sync(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage: ...

    def get_trace_sync(self, trace_id: UUID) -> RuntimeCausalTrace: ...

    def reconstruct_sync(
        self,
        request: RuntimeReconstructionRequest,
    ) -> RuntimeReconstructionReport: ...


@dataclass(slots=True)
class VellisRuntimeServices:
    """Trusted Vellis projection over runtime history, health, and reconstruction."""

    runtime: VellisRuntime
    startup_reconstruction: RuntimeReconstructionReport | None = None

    def status(self) -> JsonObject:
        messages = self._facts(RuntimeHistoryQuery(fact_type="message_accepted", limit=1000))
        terminals = self._terminal_trace_facts()
        latest = terminals[-1] if terminals else None
        return {
            "runtime_id": str(self.runtime.runtime_id),
            "runtime_key": self.runtime.runtime_key,
            "health": self.runtime.health,
            "current_position": self.runtime.current_position,
            "message_count": len(messages),
            "last_trace_id": str(latest.trace_id) if latest and latest.trace_id else None,
            "last_trace_position": latest.runtime_position if latest else None,
            "last_trace_disposition": (latest.fact_type.removeprefix("trace_") if latest else None),
        }

    def reconstruct(self, request: RuntimeReconstructionRequest) -> JsonObject:
        report = self.runtime.reconstruct_sync(request)
        self.startup_reconstruction = report
        return cast(JsonObject, encode_json(report))

    def verify_reconstruction(self, request: RuntimeReconstructionRequest) -> JsonObject:
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

    def migration_history(self) -> JsonObject:
        accepted = self._facts(
            RuntimeHistoryQuery(
                component_contract_id="component.rtg.controller",
                fact_type="message_accepted",
                limit=1000,
            )
        )
        events: list[dict[str, Any]] = []
        for fact in accepted:
            event_type = _MIGRATION_ACTIONS.get(fact.action_id or "")
            if event_type is None:
                continue
            trace = self.runtime.get_trace_sync(fact.trace_id) if fact.trace_id else None
            disposition = trace.disposition if trace else None
            terminal = trace.facts[-1] if trace and trace.facts else fact
            arguments = _fact_arguments(fact)
            events.append(
                {
                    "event_type": event_type,
                    "runtime_position": terminal.runtime_position,
                    "trace_id": str(fact.trace_id) if fact.trace_id else None,
                    "disposition": disposition.value if disposition else None,
                    "migration_id": _migration_id(fact.action_id or "", arguments),
                    "arguments": arguments,
                }
            )
        return cast(
            JsonObject,
            encode_json(
                {
                    "events": events,
                    "source": "runtime_ledger",
                    "through_runtime_position": self.runtime.current_position,
                }
            ),
        )

    def deprecated_ledger_flush_status(self) -> JsonObject:
        healthy = self.runtime.health == "ready"
        return {
            "status": "runtime_healthy" if healthy else "runtime_unavailable",
            "details": {
                "runtime_health": self.runtime.health,
                "queued_degraded_records": 0,
                "deprecated": True,
                "replacement": "runtime fail-stop health and reconstruction",
            },
        }

    def _terminal_trace_facts(self) -> tuple[RuntimeLedgerFact, ...]:
        facts: list[RuntimeLedgerFact] = []
        for disposition in RuntimeTraceDisposition:
            facts.extend(
                self._facts(
                    RuntimeHistoryQuery(
                        fact_type=f"trace_{disposition.value}",
                        limit=1000,
                    )
                )
            )
        return tuple(sorted(facts, key=lambda fact: fact.runtime_position))

    def _facts(self, query: RuntimeHistoryQuery) -> tuple[RuntimeLedgerFact, ...]:
        facts: list[RuntimeLedgerFact] = []
        after = query.after_position
        while True:
            page = self.runtime.query_history_sync(
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


def _fact_arguments(fact: RuntimeLedgerFact) -> JsonObject:
    envelope = getattr(fact, "envelope", None)
    if envelope is None or not isinstance(envelope.payload.value, dict):
        return {}
    return cast(JsonObject, envelope.payload.value)


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
