from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import sqlite3
import threading
from collections.abc import Coroutine
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from components.runtime.component_adapter.protocol import (
    ComponentRuntimeAdapter,
    RuntimeActionBindingDescriptor,
    RuntimeDispatchResult,
    RuntimeTerminalEncodingFailed,
)
from components.runtime.message_runtime.protocol import (
    ComponentOccurrenceDeclaration,
    ComponentOccurrenceRegistration,
    JsonObject,
    JsonValue,
    RuntimeActionUnknown,
    RuntimeAddress,
    RuntimeAddressUnknown,
    RuntimeCausalTrace,
    RuntimeDeliveryStatus,
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

_CURRENT_ENVELOPE: contextvars.ContextVar[RuntimeMessageEnvelope | None] = contextvars.ContextVar(
    "bibliotek_runtime_current_envelope", default=None
)
_PLAYBACK_MODE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "bibliotek_runtime_playback_mode", default=False
)
_PLAYBACK_SEVERITY: contextvars.ContextVar[list[RuntimeTraceDisposition] | None] = (
    contextvars.ContextVar("bibliotek_runtime_playback_severity", default=None)
)
_PLAYBACK_SESSION: contextvars.ContextVar[_PlaybackSession | None]


@dataclass(slots=True)
class _Delivery:
    envelope: RuntimeMessageEnvelope
    receipt: RuntimeMessageReceipt
    outcome: asyncio.Future[RuntimeRequestOutcome]


@dataclass(frozen=True, slots=True)
class _FinalizedTrace:
    root_message_id: UUID
    trace_id: UUID
    accepted_position: int
    response: RuntimeMessageEnvelope
    status: RuntimeDeliveryStatus
    terminal_position: int
    disposition: RuntimeTraceDisposition


@dataclass(slots=True)
class _TargetState:
    registration: ComponentOccurrenceRegistration
    adapter: ComponentRuntimeAdapter
    queue: asyncio.Queue[_Delivery]
    workers: list[asyncio.Task[None]]


@dataclass(slots=True)
class _PlaybackSession:
    through_position: int
    external_boundaries: dict[str, RuntimeExternalBoundaryDisposition]
    consumed_message_ids: set[UUID]


@dataclass(frozen=True, slots=True)
class _PendingBranch:
    source_runtime_id: UUID
    source_cursor: int
    verified_digest: str
    state_digests: JsonObject


_PLAYBACK_SESSION = contextvars.ContextVar("bibliotek_runtime_playback_session", default=None)


class SqliteMessageRuntime:
    """Local async message runtime with a SQLite append-only chronology."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        runtime_key: str,
        runtime_id: UUID | None = None,
    ) -> None:
        if not runtime_key.strip():
            raise RuntimeRegistrationInvalid("runtime_key must be non-empty")
        self.runtime_key = runtime_key
        resolved_database_path = Path(database_path)
        if resolved_database_path != Path(":memory:"):
            resolved_database_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = str(resolved_database_path)
        self._db_lock = threading.RLock()
        self._connection = sqlite3.connect(self._database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema(runtime_key, runtime_id)
        self.runtime_id = UUID(self._metadata("runtime_id"))
        self._health = "starting"
        self._targets: dict[UUID, _TargetState] = {}
        self._registrations_by_key: dict[str, ComponentOccurrenceRegistration] = {}
        self._pending: dict[UUID, asyncio.Future[RuntimeRequestOutcome]] = {}
        self._recovery_root_message_id: UUID | None = None
        self._pending_branch: _PendingBranch | None = None
        self._fail_next_fact_types: set[str] = set()
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name=f"bibliotek-runtime-{runtime_key}",
            daemon=True,
        )
        self._loop_thread.start()
        self._run_sync(self._initialize_runtime())

    @classmethod
    def open(
        cls,
        database_path: str | Path,
        *,
        runtime_key: str = "bibliotek.local",
        runtime_id: UUID | None = None,
    ) -> SqliteMessageRuntime:
        return cls(database_path, runtime_key=runtime_key, runtime_id=runtime_id)

    @property
    def health(self) -> str:
        return self._health

    @property
    def current_position(self) -> int:
        with self._db_lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(runtime_position), 0) AS position FROM runtime_ledger"
            ).fetchone()
        return int(row["position"])

    def current_envelope(self) -> RuntimeMessageEnvelope | None:
        return _CURRENT_ENVELOPE.get()

    def address_for(self, instance_key: str) -> RuntimeAddress:
        registration = self._registrations_by_key.get(instance_key)
        if registration is None:
            with self._db_lock:
                row = self._connection.execute(
                    "SELECT instance_id FROM runtime_occurrences WHERE instance_key = ?",
                    (instance_key,),
                ).fetchone()
            if row is None:
                raise RuntimeAddressUnknown(instance_key)
            return RuntimeAddress(self.runtime_id, UUID(row["instance_id"]))
        return RuntimeAddress(self.runtime_id, registration.instance_id)

    def allocate_registration(
        self,
        *,
        instance_key: str,
        component_contract_id: str,
        binding_id: str,
        binding_version: int,
        queue_capacity: int = 128,
        max_in_flight: int = 1,
        replay_authority: RuntimeReplayMode = RuntimeReplayMode.NO_STATE_EFFECT,
        configuration_references: tuple[str, ...] = (),
    ) -> ComponentOccurrenceRegistration:
        """Compatibility helper; the runtime, never the caller, allocates first identity."""
        with self._db_lock:
            row = self._connection.execute(
                "SELECT * FROM runtime_occurrences WHERE instance_key = ?", (instance_key,)
            ).fetchone()
        instance_id = UUID(row["instance_id"]) if row else uuid4()
        return ComponentOccurrenceRegistration(
            instance_key=instance_key,
            instance_id=instance_id,
            component_contract_id=component_contract_id,
            binding_id=binding_id,
            binding_version=binding_version,
            queue_capacity=queue_capacity,
            max_in_flight=max_in_flight,
            replay_authority=replay_authority,
            configuration_references=configuration_references,
        )

    def declare_occurrence(
        self, declaration: ComponentOccurrenceDeclaration
    ) -> ComponentOccurrenceRegistration:
        return self._run_sync(self._declare_occurrence_local(declaration))

    def register_adapter(
        self,
        *,
        instance_key: str,
        component_contract_id: str,
        adapter: ComponentRuntimeAdapter,
        queue_capacity: int = 128,
        max_in_flight: int = 1,
        replay_authority: RuntimeReplayMode | None = None,
        configuration_references: tuple[str, ...] = (),
    ) -> ComponentOccurrenceRegistration:
        description = adapter.describe()
        _validate_adapter_concurrency(description.actions, max_in_flight)
        declared_replay_authority = replay_authority or _binding_replay_authority(
            description.actions
        )
        if declared_replay_authority is not _binding_replay_authority(description.actions):
            raise RuntimeRegistrationInvalid(
                "registration replay authority differs from binding actions"
            )
        registration = self.allocate_registration(
            instance_key=instance_key,
            component_contract_id=component_contract_id,
            binding_id=description.binding_id,
            binding_version=description.binding_version,
            queue_capacity=queue_capacity,
            max_in_flight=max_in_flight,
            replay_authority=declared_replay_authority,
            configuration_references=configuration_references,
        )
        self._run_sync(self._register_occurrence_local(registration))
        self._run_sync(self._attach_adapter_local(registration, adapter))
        return registration

    def register_source_occurrence(
        self,
        *,
        instance_key: str,
        component_contract_id: str,
        binding_id: str,
        binding_version: int = 1,
        replay_authority: RuntimeReplayMode = RuntimeReplayMode.EXTERNAL_EXCHANGE,
        configuration_references: tuple[str, ...] = (),
    ) -> ComponentOccurrenceRegistration:
        registration = self.allocate_registration(
            instance_key=instance_key,
            component_contract_id=component_contract_id,
            binding_id=binding_id,
            binding_version=binding_version,
            queue_capacity=1,
            max_in_flight=1,
            replay_authority=replay_authority,
            configuration_references=configuration_references,
        )
        resolved = self.register_occurrence_sync(registration)
        self._run_sync(self._activate_source_local(resolved))
        return resolved

    async def register_occurrence(
        self,
        declaration: ComponentOccurrenceDeclaration | ComponentOccurrenceRegistration,
    ) -> ComponentOccurrenceRegistration:
        if isinstance(declaration, ComponentOccurrenceRegistration):
            registration = declaration
        else:
            return await self._run_async(self._declare_occurrence_local(declaration))
        return await self._run_async(self._register_occurrence_local(registration))

    def register_occurrence_sync(
        self,
        registration: ComponentOccurrenceDeclaration | ComponentOccurrenceRegistration,
    ) -> ComponentOccurrenceRegistration:
        if isinstance(registration, ComponentOccurrenceDeclaration):
            return self._run_sync(self._declare_occurrence_local(registration))
        return self._run_sync(self._register_occurrence_local(registration))

    def attach_adapter(
        self,
        registration: ComponentOccurrenceRegistration,
        adapter: ComponentRuntimeAdapter,
    ) -> None:
        self._run_sync(self._attach_adapter_local(registration, adapter))

    async def prepare_static_topology(self, manifest: RuntimeTopologyManifest) -> None:
        await self._run_async(self._prepare_static_topology_local(manifest))

    def prepare_static_topology_sync(self, manifest: RuntimeTopologyManifest) -> None:
        self._run_sync(self._prepare_static_topology_local(manifest))

    async def confirm_static_topology(
        self,
        manifest: RuntimeTopologyManifest | None = None,
        *,
        expected_occurrences: tuple[ComponentOccurrenceDeclaration, ...] = (),
        manifest_hash: str = "",
        expected_instance_keys: tuple[str, ...] = (),
    ) -> RuntimeTopologyConfirmation:
        if manifest is not None:
            expected_occurrences = manifest.occurrences
            manifest_hash = manifest.manifest_hash
        return await self._run_async(
            self._confirm_static_topology_local(
                expected_occurrences, expected_instance_keys, manifest_hash, manifest
            )
        )

    def confirm_static_topology_sync(
        self,
        manifest: RuntimeTopologyManifest | None = None,
        *,
        expected_occurrences: tuple[ComponentOccurrenceDeclaration, ...] = (),
        manifest_hash: str = "",
        expected_instance_keys: tuple[str, ...] = (),
    ) -> RuntimeTopologyConfirmation:
        if manifest is not None:
            expected_occurrences = manifest.occurrences
            manifest_hash = manifest.manifest_hash
        return self._run_sync(
            self._confirm_static_topology_local(
                expected_occurrences, expected_instance_keys, manifest_hash, manifest
            )
        )

    async def send(self, message: RuntimeMessageEnvelope) -> RuntimeMessageReceipt:
        if _PLAYBACK_MODE.get():
            outcome = await self._run_async(self._playback_request_local(message))
            return outcome.request
        receipt, _, _ = await self._run_async(self._accept_local(message))
        return receipt

    async def request(
        self,
        message: RuntimeMessageEnvelope,
        timeout_seconds: float | None = None,
    ) -> RuntimeRequestOutcome:
        if _PLAYBACK_MODE.get():
            return await self._run_async(self._playback_request_local(message))
        return await self._run_async(self._request_local(message, timeout_seconds))

    def request_sync(
        self,
        message: RuntimeMessageEnvelope,
        timeout_seconds: float | None = None,
    ) -> RuntimeRequestOutcome:
        if _PLAYBACK_MODE.get():
            return self._run_sync(self._playback_request_local(message))
        return self._run_sync(self._request_local(message, timeout_seconds))

    async def query_history(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage:
        return await self._run_async(self._query_history_local(query))

    def query_history_sync(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage:
        return self._run_sync(self._query_history_local(query))

    async def get_trace(self, trace_id: UUID) -> RuntimeCausalTrace:
        return await self._run_async(self._get_trace_local(trace_id))

    def get_trace_sync(self, trace_id: UUID) -> RuntimeCausalTrace:
        return self._run_sync(self._get_trace_local(trace_id))

    async def reconstruct(
        self, request: RuntimeReconstructionRequest
    ) -> RuntimeReconstructionReport:
        return await self._run_async(self._reconstruct_local(request))

    def reconstruct_sync(
        self, request: RuntimeReconstructionRequest
    ) -> RuntimeReconstructionReport:
        return self._run_sync(self._reconstruct_local(request))

    async def record_branch_provenance(
        self,
        *,
        source_runtime_id: UUID,
        source_cursor: int,
        verified_digest: str,
    ) -> int:
        return await self._run_async(
            self._record_branch_provenance_local(
                source_runtime_id=source_runtime_id,
                source_cursor=source_cursor,
                verified_digest=verified_digest,
            )
        )

    def record_branch_provenance_sync(
        self,
        *,
        source_runtime_id: UUID,
        source_cursor: int,
        verified_digest: str,
    ) -> int:
        return self._run_sync(
            self._record_branch_provenance_local(
                source_runtime_id=source_runtime_id,
                source_cursor=source_cursor,
                verified_digest=verified_digest,
            )
        )

    async def _record_branch_provenance_local(
        self,
        *,
        source_runtime_id: UUID,
        source_cursor: int,
        verified_digest: str,
    ) -> int:
        if self._health == "fail_stopped":
            self._ensure_healthy()
        pending = self._pending_branch
        if self._health != "branch_pending" or pending is None:
            raise RuntimeReplayIncompatible(
                "branch provenance requires a verified historical reconstruction"
            )
        if source_cursor < 0:
            raise RuntimeReplayIncompatible("branch source cursor must be non-negative")
        if len(verified_digest) != 64 or any(
            character not in "0123456789abcdef" for character in verified_digest
        ):
            raise RuntimeReplayIncompatible(
                "branch provenance requires a lowercase SHA-256 verified digest"
            )
        if (
            source_runtime_id != pending.source_runtime_id
            or source_cursor != pending.source_cursor
            or verified_digest != pending.verified_digest
        ):
            raise RuntimeReplayIncompatible(
                "branch provenance does not match the verified historical reconstruction"
            )
        actual_state_digests: JsonObject = {}
        for instance_key, expected_digest in pending.state_digests.items():
            registration = self._registrations_by_key.get(instance_key)
            target = (
                self._targets.get(registration.instance_id)
                if registration is not None
                else None
            )
            if target is None:
                raise RuntimeReplayTargetNotPrepared(
                    f"branch state owner is not attached: {instance_key}"
                )
            actual_digest = await target.adapter.replay_state_digest()
            actual_state_digests[instance_key] = actual_digest
            if actual_digest != expected_digest:
                raise RuntimeReplayTargetNotPrepared(
                    f"branch state digest differs for {instance_key}"
                )
        if _state_digests_digest(actual_state_digests) != pending.verified_digest:
            raise RuntimeReplayTargetNotPrepared(
                "combined branch state digest differs from verified reconstruction"
            )
        try:
            position = self._append_fact(
                "branch_provenance",
                details={
                    "source_runtime_id": str(source_runtime_id),
                    "source_cursor": source_cursor,
                    "verified_digest": verified_digest,
                },
            )
        except RuntimeLedgerUnavailable as error:
            self._health = "fail_stopped"
            raise RuntimeFailStopped(
                "branch provenance could not be durably recorded"
            ) from error
        self._pending_branch = None
        self._health = "ready"
        return position

    def simulate_ledger_failure_once(self, fact_type: str) -> None:
        """Inject one deterministic append failure for black-box failure-path verification."""
        self._fail_next_fact_types.add(fact_type)

    def close(self) -> None:
        if self._health == "closed":
            return
        try:
            self._run_sync(self._close_local())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=5)
            with self._db_lock:
                self._connection.close()
            self._health = "closed"

    def __enter__(self) -> SqliteMessageRuntime:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _run_async(self, coroutine: Coroutine[object, object, Any]) -> Any:
        if asyncio.get_running_loop() is self._loop:
            return await coroutine
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return await asyncio.wrap_future(future)

    def _run_sync(self, coroutine: Coroutine[object, object, Any]) -> Any:
        if threading.current_thread() is self._loop_thread:
            raise RuntimeError(
                "synchronous runtime calls cannot block the runtime event-loop thread"
            )
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def _initialize_schema(self, runtime_key: str, runtime_id: UUID | None) -> None:
        with self._db_lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_occurrences (
                    instance_key TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL UNIQUE,
                    component_contract_id TEXT NOT NULL,
                    binding_id TEXT NOT NULL,
                    binding_version INTEGER NOT NULL,
                    queue_capacity INTEGER NOT NULL,
                    max_in_flight INTEGER NOT NULL,
                    replay_authority TEXT NOT NULL DEFAULT 'no_state_effect',
                    configuration_references_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    registered_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_ledger (
                    runtime_position INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact_type TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    runtime_id TEXT NOT NULL,
                    instance_key TEXT,
                    instance_id TEXT,
                    component_contract_id TEXT,
                    message_id TEXT,
                    trace_id TEXT,
                    correlation_id TEXT,
                    causation_id TEXT,
                    action_id TEXT,
                    schema_version INTEGER,
                    details_json TEXT NOT NULL,
                    envelope_json TEXT
                );
                CREATE TABLE IF NOT EXISTS runtime_messages (
                    message_id TEXT PRIMARY KEY,
                    envelope_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    accepted_position INTEGER NOT NULL,
                    terminal_position INTEGER,
                    response_json TEXT,
                    trace_disposition TEXT
                );
                CREATE INDEX IF NOT EXISTS runtime_ledger_trace_idx
                    ON runtime_ledger(trace_id, runtime_position);
                CREATE INDEX IF NOT EXISTS runtime_ledger_instance_idx
                    ON runtime_ledger(instance_id, runtime_position);
                CREATE INDEX IF NOT EXISTS runtime_ledger_message_idx
                    ON runtime_ledger(message_id, runtime_position);
                """
            )
            columns = {
                str(row["name"])
                for row in self._connection.execute(
                    "PRAGMA table_info(runtime_occurrences)"
                ).fetchall()
            }
            if "replay_authority" not in columns:
                self._connection.execute(
                    "ALTER TABLE runtime_occurrences ADD COLUMN replay_authority TEXT "
                    "NOT NULL DEFAULT 'no_state_effect'"
                )
            if "configuration_references_json" not in columns:
                self._connection.execute(
                    "ALTER TABLE runtime_occurrences ADD COLUMN "
                    "configuration_references_json TEXT NOT NULL DEFAULT '[]'"
                )
            existing_key = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'runtime_key'"
            ).fetchone()
            if existing_key and existing_key["value"] != runtime_key:
                raise RuntimeRegistrationInvalid(
                    f"data root belongs to runtime_key={existing_key['value']!r}"
                )
            existing_id = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'runtime_id'"
            ).fetchone()
            if existing_id and runtime_id and existing_id["value"] != str(runtime_id):
                raise RuntimeRegistrationInvalid(
                    "supplied runtime_id conflicts with durable identity"
                )
            self._connection.execute(
                "INSERT OR IGNORE INTO runtime_metadata(key, value) VALUES ('runtime_key', ?)",
                (runtime_key,),
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO runtime_metadata(key, value) VALUES ('runtime_id', ?)",
                (str(runtime_id or uuid4()),),
            )

    def _metadata(self, key: str) -> str:
        with self._db_lock:
            row = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            raise RuntimeRegistrationInvalid(f"runtime metadata is missing: {key}")
        return str(row["value"])

    async def _initialize_runtime(self) -> None:
        self._load_registrations()
        recovery_required = self._recover_incomplete_messages()
        recovery_required = self._durable_recovery_required() or recovery_required
        self._pending_branch = self._load_pending_branch()
        self._health = (
            "branch_pending"
            if self._pending_branch is not None
            else "recovery_required"
            if recovery_required
            else "ready"
        )
        self._append_fact(
            "runtime_initialized",
            details={
                "runtime_key": self.runtime_key,
                "database_path": self._database_path,
                "recovery_required": recovery_required,
                "branch_provenance_pending": self._pending_branch is not None,
            },
        )

    def _load_registrations(self) -> None:
        with self._db_lock:
            rows = self._connection.execute("SELECT * FROM runtime_occurrences").fetchall()
        for row in rows:
            registration = _registration_from_row(row)
            self._registrations_by_key[registration.instance_key] = registration

    def _recover_incomplete_messages(self) -> bool:
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT message_id FROM runtime_messages WHERE terminal_position IS NULL"
            ).fetchall()
        for row in rows:
            message_id = UUID(row["message_id"])
            with self._db_lock, self._connection:
                ledger = self._connection.execute(
                    "SELECT trace_id, envelope_json FROM runtime_ledger "
                    "WHERE message_id = ? AND envelope_json IS NOT NULL "
                    "ORDER BY runtime_position LIMIT 1",
                    (str(message_id),),
                ).fetchone()
                trace_id = UUID(ledger["trace_id"]) if ledger and ledger["trace_id"] else None
                response_json = None
                if ledger and ledger["envelope_json"]:
                    request = _decode_envelope(json.loads(ledger["envelope_json"]))
                    response = _runtime_fault_result(
                        request,
                        RuntimeFailStopped(
                            "runtime restarted without a confirmed terminal outcome"
                        ),
                    ).response
                    response_json = _canonical_json(_encode(response))
                position = self._insert_fact(
                    "trace_indeterminate",
                    message_id=message_id,
                    trace_id=trace_id,
                    details={"reason": "runtime restarted without a confirmed terminal outcome"},
                )
                self._connection.execute(
                    "UPDATE runtime_messages SET status = ?, terminal_position = ?, "
                    "response_json = ?, trace_disposition = ? WHERE message_id = ?",
                    (
                        RuntimeDeliveryStatus.FAULTED.value,
                        position,
                        response_json,
                        RuntimeTraceDisposition.INDETERMINATE.value,
                        str(message_id),
                    ),
                )
        return bool(rows)

    def _durable_recovery_required(self) -> bool:
        """Return whether confirmed history still requires reconstruction.

        A successful reconstruction is the only durable fact that clears an earlier
        indeterminate trace or reconstruction. This keeps the recovery ingress gate
        closed across process restarts even when the best-effort fail-stop marker was
        itself able to terminalize the affected message row.
        """

        with self._db_lock:
            row = self._connection.execute(
                """
                SELECT
                    COALESCE(MAX(CASE WHEN fact_type IN (
                        'trace_indeterminate',
                        'runtime_recovery_required',
                        'reconstruction_indeterminate'
                    ) THEN runtime_position END), 0) AS required_position,
                    COALESCE(MAX(CASE WHEN fact_type = 'reconstruction_completed'
                        THEN runtime_position END), 0) AS completed_position
                FROM runtime_ledger
                """
            ).fetchone()
        return bool(
            row is not None
            and int(row["required_position"]) > int(row["completed_position"])
        )

    def _load_pending_branch(self) -> _PendingBranch | None:
        with self._db_lock:
            required = self._connection.execute(
                "SELECT runtime_position, details_json FROM runtime_ledger "
                "WHERE fact_type = 'branch_provenance_required' "
                "ORDER BY runtime_position DESC LIMIT 1"
            ).fetchone()
            recorded = self._connection.execute(
                "SELECT runtime_position FROM runtime_ledger "
                "WHERE fact_type = 'branch_provenance' "
                "ORDER BY runtime_position DESC LIMIT 1"
            ).fetchone()
        if required is None or (
            recorded is not None
            and int(recorded["runtime_position"]) > int(required["runtime_position"])
        ):
            return None
        details = json.loads(str(required["details_json"]))
        state_digests = details.get("state_digests")
        if not isinstance(state_digests, dict):
            raise RuntimeReplayIncompatible(
                "durable branch requirement has malformed state digests"
            )
        return _PendingBranch(
            source_runtime_id=UUID(str(details["source_runtime_id"])),
            source_cursor=int(details["source_cursor"]),
            verified_digest=str(details["verified_digest"]),
            state_digests=cast(JsonObject, state_digests),
        )

    async def _register_occurrence_local(
        self, registration: ComponentOccurrenceRegistration
    ) -> ComponentOccurrenceRegistration:
        self._ensure_healthy(allow_recovery=True, allow_branch_pending=True)
        _validate_registration(registration)
        self._preflight_static_registration(registration)
        with self._db_lock:
            key_row = self._connection.execute(
                "SELECT * FROM runtime_occurrences WHERE instance_key = ?",
                (registration.instance_key,),
            ).fetchone()
            id_row = self._connection.execute(
                "SELECT * FROM runtime_occurrences WHERE instance_id = ?",
                (str(registration.instance_id),),
            ).fetchone()
        if key_row is not None:
            existing = _registration_from_row(key_row)
            if existing != registration:
                raise RuntimeRegistrationInvalid(
                    "static occurrence topology changed without migration: "
                    f"{registration.instance_key}"
                )
            self._registrations_by_key[registration.instance_key] = existing
            return existing
        if id_row is not None:
            raise RuntimeRegistrationInvalid(
                f"instance UUID already belongs to {id_row['instance_key']}"
            )
        try:
            with self._db_lock, self._connection:
                self._connection.execute(
                    "INSERT INTO runtime_occurrences(instance_key, instance_id, "
                    "component_contract_id, binding_id, binding_version, queue_capacity, "
                    "max_in_flight, replay_authority, configuration_references_json, "
                    "status, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        registration.instance_key,
                        str(registration.instance_id),
                        registration.component_contract_id,
                        registration.binding_id,
                        registration.binding_version,
                        registration.queue_capacity,
                        registration.max_in_flight,
                        registration.replay_authority.value,
                        _canonical_json(list(registration.configuration_references)),
                        "registered",
                        _now(),
                    ),
                )
                self._insert_fact(
                    "occurrence_registered",
                    registration=registration,
                    details={
                        "binding_id": registration.binding_id,
                        "binding_version": registration.binding_version,
                        "queue_capacity": registration.queue_capacity,
                        "max_in_flight": registration.max_in_flight,
                        "replay_authority": registration.replay_authority.value,
                        "configuration_references": list(registration.configuration_references),
                    },
                )
        except sqlite3.Error as error:
            raise RuntimeLedgerUnavailable(str(error)) from error
        self._registrations_by_key[registration.instance_key] = registration
        return registration

    async def _declare_occurrence_local(
        self, declaration: ComponentOccurrenceDeclaration
    ) -> ComponentOccurrenceRegistration:
        _validate_declaration(declaration)
        with self._db_lock:
            row = self._connection.execute(
                "SELECT * FROM runtime_occurrences WHERE instance_key = ?",
                (declaration.instance_key,),
            ).fetchone()
        if row is not None:
            existing = _registration_from_row(row)
            if _declaration_from_registration(existing) != declaration:
                raise RuntimeRegistrationInvalid(
                    "static occurrence topology changed without migration: "
                    f"{declaration.instance_key}"
                )
            self._registrations_by_key[existing.instance_key] = existing
            return existing
        registration = ComponentOccurrenceRegistration(
            instance_key=declaration.instance_key,
            instance_id=uuid4(),
            component_contract_id=declaration.component_contract_id,
            binding_id=declaration.binding_id,
            binding_version=declaration.binding_version,
            queue_capacity=declaration.queue_capacity,
            max_in_flight=declaration.max_in_flight,
            replay_authority=declaration.replay_authority,
            configuration_references=declaration.configuration_references,
        )
        return await self._register_occurrence_local(registration)

    async def _prepare_static_topology_local(
        self, manifest: RuntimeTopologyManifest
    ) -> None:
        self._ensure_healthy(allow_recovery=True, allow_branch_pending=True)
        _validate_static_topology_manifest(manifest, runtime_key=self.runtime_key)
        plan = _static_topology_plan(manifest)
        encoded_plan = _canonical_json(plan)
        with self._db_lock:
            prepared = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'static_topology_plan'"
            ).fetchone()
            confirmed = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'static_topology_hash'"
            ).fetchone()
            rows = self._connection.execute(
                "SELECT * FROM runtime_occurrences ORDER BY instance_key"
            ).fetchall()
        if prepared is not None:
            if str(prepared["value"]) != encoded_plan:
                raise RuntimeRegistrationInvalid(
                    "static occurrence contract changed without topology migration: "
                    "preparation differs from the durable topology plan"
                )
            return
        if confirmed is not None:
            actual_declarations = tuple(
                _declaration_from_registration(_registration_from_row(row)) for row in rows
            )
            expected_declarations = tuple(
                sorted(manifest.occurrences, key=lambda item: item.instance_key)
            )
            if actual_declarations != expected_declarations:
                raise RuntimeRegistrationInvalid(
                    "static occurrence topology changed without migration"
                )
            # A runtime confirmed before topology plans were persisted is guarded by
            # its durable rows and hash. Confirmation will install the full plan only
            # after also proving curated-operation compatibility.
            return
        try:
            with self._db_lock, self._connection:
                self._connection.execute(
                    "INSERT INTO runtime_metadata(key, value) "
                    "VALUES ('static_topology_plan', ?)",
                    (encoded_plan,),
                )
                self._insert_fact(
                    "topology_prepared",
                    details={
                        "topology_plan_hash": _topology_plan_hash(plan),
                        "topology_plan": plan,
                    },
                )
        except sqlite3.Error as error:
            raise RuntimeLedgerUnavailable(str(error)) from error

    def _preflight_static_registration(
        self, registration: ComponentOccurrenceRegistration
    ) -> None:
        declaration = _declaration_from_registration(registration)
        with self._db_lock:
            prepared = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'static_topology_plan'"
            ).fetchone()
            confirmed = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'static_topology_hash'"
            ).fetchone()
            confirmed_row = (
                self._connection.execute(
                    "SELECT * FROM runtime_occurrences WHERE instance_key = ?",
                    (registration.instance_key,),
                ).fetchone()
                if prepared is None and confirmed is not None
                else None
            )
        if prepared is not None:
            planned_declarations = _topology_plan_declarations(str(prepared["value"]))
            expected = planned_declarations.get(registration.instance_key)
            if expected is None:
                raise RuntimeRegistrationInvalid(
                    "static occurrence topology changed without migration: "
                    f"{registration.instance_key}"
                )
            if expected != declaration:
                raise RuntimeRegistrationInvalid(
                    "static occurrence topology changed without migration: "
                    f"{registration.instance_key}"
                )
            return
        if confirmed is not None:
            if confirmed_row is None or (
                _declaration_from_registration(_registration_from_row(confirmed_row))
                != declaration
            ):
                raise RuntimeRegistrationInvalid(
                    "static occurrence topology changed without migration: "
                    f"{registration.instance_key}"
                )

    async def _attach_adapter_local(
        self,
        registration: ComponentOccurrenceRegistration,
        adapter: ComponentRuntimeAdapter,
    ) -> None:
        if registration.instance_id in self._targets:
            raise RuntimeRegistrationInvalid(
                f"occurrence is already attached: {registration.instance_key}"
            )
        description = adapter.describe()
        if (
            description.binding_id != registration.binding_id
            or description.binding_version != registration.binding_version
        ):
            raise RuntimeRegistrationInvalid("adapter binding identity differs from registration")
        if any(
            action.component_contract_id != registration.component_contract_id
            for action in description.actions
        ):
            raise RuntimeRegistrationInvalid("adapter component contract differs from registration")
        expected_replay_authority = _binding_replay_authority(description.actions)
        if registration.replay_authority is not expected_replay_authority:
            raise RuntimeRegistrationInvalid(
                "registration replay authority differs from binding actions: "
                f"{registration.replay_authority.value} != "
                f"{expected_replay_authority.value}"
            )
        _validate_adapter_concurrency(description.actions, registration.max_in_flight)
        queue: asyncio.Queue[_Delivery] = asyncio.Queue(registration.queue_capacity)
        target = _TargetState(registration, adapter, queue, [])
        self._targets[registration.instance_id] = target
        target.workers.extend(
            asyncio.create_task(
                self._worker(target),
                name=f"{registration.instance_key}-worker-{index}",
            )
            for index in range(registration.max_in_flight)
        )
        with self._db_lock, self._connection:
            self._connection.execute(
                "UPDATE runtime_occurrences SET status = 'ready' WHERE instance_key = ?",
                (registration.instance_key,),
            )
            self._insert_fact("occurrence_ready", registration=registration)

    async def _activate_source_local(self, registration: ComponentOccurrenceRegistration) -> None:
        with self._db_lock, self._connection:
            row = self._connection.execute(
                "SELECT status FROM runtime_occurrences WHERE instance_key = ?",
                (registration.instance_key,),
            ).fetchone()
            if row is None:
                raise RuntimeRegistrationInvalid(registration.instance_key)
            if row["status"] == "ready":
                return
            self._connection.execute(
                "UPDATE runtime_occurrences SET status = 'ready' WHERE instance_key = ?",
                (registration.instance_key,),
            )
            self._insert_fact(
                "occurrence_ready",
                registration=registration,
                details={"source_only": True},
            )

    async def _confirm_static_topology_local(
        self,
        expected_occurrences: tuple[ComponentOccurrenceDeclaration, ...],
        expected_instance_keys: tuple[str, ...],
        manifest_hash: str,
        manifest: RuntimeTopologyManifest | None,
    ) -> RuntimeTopologyConfirmation:
        self._ensure_healthy(allow_recovery=True, allow_branch_pending=True)
        topology_plan: JsonObject | None = None
        if manifest is not None:
            _validate_static_topology_manifest(manifest, runtime_key=self.runtime_key)
            topology_plan = _static_topology_plan(manifest)
            with self._db_lock:
                prepared = self._connection.execute(
                    "SELECT value FROM runtime_metadata "
                    "WHERE key = 'static_topology_plan'"
                ).fetchone()
            if prepared is not None and str(prepared["value"]) != _canonical_json(
                topology_plan
            ):
                raise RuntimeRegistrationInvalid(
                    "static occurrence contract changed without topology migration: "
                    "confirmation differs from the durable topology plan"
                )
            for operation in manifest.curated_operations:
                registration = self._registrations_by_key.get(operation.target_instance_key)
                target = (
                    self._targets.get(registration.instance_id)
                    if registration is not None
                    else None
                )
                if target is None:
                    raise RuntimeRegistrationInvalid(
                        f"curated operation target has no attached adapter: "
                        f"{operation.operation_id}"
                    )
                action = next(
                    (
                        item
                        for item in target.adapter.describe().actions
                        if item.action_id == operation.action_id
                    ),
                    None,
                )
                if action is None or action.schema_version != operation.schema_version:
                    raise RuntimeRegistrationInvalid(
                        f"curated operation action/schema is not registered: "
                        f"{operation.operation_id}"
                    )
        if expected_occurrences and expected_instance_keys:
            raise RuntimeRegistrationInvalid(
                "provide complete expected_occurrences, not both topology forms"
            )
        if expected_occurrences:
            for declaration in expected_occurrences:
                _validate_declaration(declaration)
            expected = {item.instance_key for item in expected_occurrences}
            if len(expected) != len(expected_occurrences):
                raise RuntimeRegistrationInvalid("static occurrence keys must be unique")
        else:
            expected = set(expected_instance_keys)
        if (
            not expected
            or (not expected_occurrences and len(expected) != len(expected_instance_keys))
            or any(not key.strip() for key in expected)
        ):
            raise RuntimeRegistrationInvalid("static topology keys must be non-empty and unique")
        if len(manifest_hash) != 64 or any(
            character not in "0123456789abcdef" for character in manifest_hash
        ):
            raise RuntimeRegistrationInvalid("manifest_hash must be a lowercase SHA-256 digest")
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT * FROM runtime_occurrences ORDER BY instance_key"
            ).fetchall()
        actual = {str(row["instance_key"]) for row in rows}
        if actual != expected:
            raise RuntimeRegistrationInvalid(
                "static occurrence topology changed without migration: "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )
        actual_declarations = tuple(
            _declaration_from_registration(_registration_from_row(row)) for row in rows
        )
        if expected_occurrences and actual_declarations != tuple(
            sorted(expected_occurrences, key=lambda item: item.instance_key)
        ):
            expected_by_key = {item.instance_key: item for item in expected_occurrences}
            differences = [
                key
                for key in sorted(expected)
                if _declaration_from_registration(
                    _registration_from_row(next(row for row in rows if row["instance_key"] == key))
                )
                != expected_by_key[key]
            ]
            raise RuntimeRegistrationInvalid(
                f"static occurrence contract changed without topology migration: {differences}"
            )
        topology_value: JsonValue = {
            "runtime_key": self.runtime_key,
            "manifest_schema_version": (
                manifest.manifest_schema_version if manifest is not None else 1
            ),
            "occurrences": [
                {
                    "instance_key": str(row["instance_key"]),
                    "instance_id": str(row["instance_id"]),
                    "component_contract_id": str(row["component_contract_id"]),
                    "binding_id": str(row["binding_id"]),
                    "binding_version": int(row["binding_version"]),
                    "queue_capacity": int(row["queue_capacity"]),
                    "max_in_flight": int(row["max_in_flight"]),
                    "replay_authority": str(row["replay_authority"]),
                    "configuration_references": json.loads(row["configuration_references_json"]),
                }
                for row in rows
            ],
            "curated_operations": [
                cast(JsonValue, _encode(operation))
                for operation in (manifest.curated_operations if manifest is not None else ())
            ],
        }
        topology_hash = hashlib.sha256(_canonical_json(topology_value).encode("utf-8")).hexdigest()
        recovery_required = self._committed_canonical_history_exists()
        with self._db_lock, self._connection:
            recorded = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'static_topology_hash'"
            ).fetchone()
            if recorded is not None and recorded["value"] != topology_hash:
                raise RuntimeRegistrationInvalid(
                    "static occurrence identity or binding changed without topology migration"
                )
            self._connection.execute(
                "INSERT OR IGNORE INTO runtime_metadata(key, value) "
                "VALUES ('static_topology_hash', ?)",
                (topology_hash,),
            )
            if topology_plan is not None:
                self._connection.execute(
                    "INSERT OR IGNORE INTO runtime_metadata(key, value) "
                    "VALUES ('static_topology_plan', ?)",
                    (_canonical_json(topology_plan),),
                )
            self._connection.execute(
                "INSERT INTO runtime_metadata(key, value) "
                "VALUES ('application_manifest_hash', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (manifest_hash,),
            )
            self._insert_fact(
                "topology_confirmed",
                details={
                    "manifest_hash": manifest_hash,
                    "topology_hash": topology_hash,
                    "topology_plan_hash": (
                        _topology_plan_hash(topology_plan)
                        if topology_plan is not None
                        else None
                    ),
                    "topology_plan": topology_plan,
                    "occurrence_count": len(rows),
                    "recovery_required": recovery_required,
                },
            )
            if recovery_required:
                self._insert_fact(
                    "runtime_recovery_required",
                    details={"reason": "committed canonical history awaits reconstruction"},
                )
        if recovery_required and self._health != "branch_pending":
            self._health = "recovery_required"
        return RuntimeTopologyConfirmation(manifest_hash, topology_hash, len(rows))

    def _committed_canonical_history_exists(self) -> bool:
        with self._db_lock:
            row = self._connection.execute(
                """
                SELECT 1 FROM runtime_ledger AS effect
                WHERE effect.fact_type = 'canonical_effect'
                  AND 'trace_committed' = (
                    SELECT terminal.fact_type FROM runtime_ledger AS terminal
                    WHERE terminal.trace_id = effect.trace_id
                      AND terminal.fact_type IN (
                        'trace_committed', 'trace_aborted', 'trace_indeterminate'
                      )
                    ORDER BY terminal.runtime_position DESC
                    LIMIT 1
                  )
                LIMIT 1
                """
            ).fetchone()
        return row is not None

    async def _accept_local(
        self, message: RuntimeMessageEnvelope
    ) -> tuple[
        RuntimeMessageReceipt,
        RuntimeRequestOutcome | None,
        asyncio.Future[RuntimeRequestOutcome] | None,
    ]:
        try:
            if message.kind not in {
                RuntimeMessageKind.REQUEST,
                RuntimeMessageKind.SIGNAL,
            }:
                raise RuntimeRegistrationInvalid(
                    "runtime dispatch accepts only request or signal envelopes"
                )
            _require_canonical_json_value(message.payload.value, path="payload.value")
            envelope_json = _canonical_json(_encode(message))
            message = _decode_envelope(json.loads(envelope_json))
        except Exception as error:
            self._record_message_rejection(message, error)
            raise
        envelope_hash = hashlib.sha256(envelope_json.encode()).hexdigest()
        with self._db_lock:
            existing = self._connection.execute(
                "SELECT * FROM runtime_messages WHERE message_id = ?",
                (str(message.message_id),),
            ).fetchone()
        if existing is not None:
            if existing["envelope_hash"] != envelope_hash:
                self._record_message_rejection(
                    message,
                    RuntimeMessageConflict(str(message.message_id)),
                )
                raise RuntimeMessageConflict(str(message.message_id))
            receipt = RuntimeMessageReceipt(
                message_id=message.message_id,
                trace_id=message.trace_id,
                accepted_position=int(existing["accepted_position"]),
                status=RuntimeDeliveryStatus(existing["status"]),
            )
            if existing["terminal_position"] is not None and existing["response_json"]:
                response = _decode_envelope(json.loads(existing["response_json"]))
                return (
                    receipt,
                    RuntimeRequestOutcome(
                        request=receipt,
                        response=response,
                        terminal_position=int(existing["terminal_position"]),
                        trace_disposition=RuntimeTraceDisposition(existing["trace_disposition"]),
                    ),
                    None,
                )
            return receipt, None, self._pending.get(message.message_id)

        reserved_recovery_root = False
        try:
            target = self._validate_target(message)
            descriptor = next(
                action
                for action in target.adapter.describe().actions
                if action.action_id == message.action_id
            )
            recovery_root = (
                message.kind is RuntimeMessageKind.REQUEST
                and message.causation_id is None
                and descriptor.recovery_authorized
            )
            self._ensure_healthy(allow_recovery=recovery_root)
            self._validate_causality(message)
            if recovery_root:
                if self._recovery_root_message_id not in {None, message.message_id}:
                    raise RuntimeFailStopped(
                        "recovery ingress is already reserved by another root request"
                    )
                self._recovery_root_message_id = message.message_id
                reserved_recovery_root = True
        except Exception as error:
            self._record_message_rejection(message, error)
            raise

        if target.queue.full():
            if reserved_recovery_root:
                self._release_recovery_root(message.message_id)
            self._record_message_rejection(
                message, RuntimeQueueFull(target.registration.instance_key)
            )
            raise RuntimeQueueFull(target.registration.instance_key)
        try:
            with self._db_lock, self._connection:
                position = self._insert_fact(
                    "message_accepted",
                    registration=target.registration,
                    envelope=message,
                    details={"envelope_hash": envelope_hash},
                )
                self._connection.execute(
                    "INSERT INTO runtime_messages(message_id, envelope_hash, status, "
                    "accepted_position) VALUES (?, ?, ?, ?)",
                    (
                        str(message.message_id),
                        envelope_hash,
                        RuntimeDeliveryStatus.ACCEPTED.value,
                        position,
                    ),
                )
        except sqlite3.Error as error:
            if reserved_recovery_root:
                self._release_recovery_root(message.message_id)
            raise RuntimeLedgerUnavailable(str(error)) from error

        receipt = RuntimeMessageReceipt(
            message_id=message.message_id,
            trace_id=message.trace_id,
            accepted_position=position,
            status=RuntimeDeliveryStatus.ACCEPTED,
        )
        outcome: asyncio.Future[RuntimeRequestOutcome] = self._loop.create_future()
        self._pending[message.message_id] = outcome
        target.queue.put_nowait(_Delivery(message, receipt, outcome))
        return receipt, None, outcome

    def _record_message_rejection(self, message: RuntimeMessageEnvelope, error: Exception) -> None:
        details: JsonObject = {
            "failure_type": type(error).__name__,
            "message": str(error),
        }
        try:
            self._append_fact(
                "message_rejected",
                envelope=message,
                details=details,
            )
        except TypeError, ValueError:
            details.update(
                {
                    "message_id": str(message.message_id),
                    "trace_id": str(message.trace_id),
                    "envelope_unavailable": True,
                }
            )
            self._append_fact("message_rejected", details=details)

    def _validate_causality(self, message: RuntimeMessageEnvelope) -> None:
        with self._db_lock:
            if message.causation_id is None:
                existing_root = self._connection.execute(
                    "SELECT message_id FROM runtime_ledger "
                    "WHERE fact_type = 'message_accepted' AND trace_id = ? "
                    "AND causation_id IS NULL LIMIT 1",
                    (str(message.trace_id),),
                ).fetchone()
                if existing_root is not None and existing_root["message_id"] != str(
                    message.message_id
                ):
                    raise RuntimeRegistrationInvalid(
                        f"trace already has a root message: {message.trace_id}"
                    )
                return
            parent = self._connection.execute(
                "SELECT trace_id FROM runtime_ledger "
                "WHERE fact_type = 'message_accepted' AND message_id = ? LIMIT 1",
                (str(message.causation_id),),
            ).fetchone()
            terminal = self._connection.execute(
                "SELECT 1 FROM runtime_ledger WHERE trace_id = ? "
                "AND fact_type IN ('trace_committed', 'trace_aborted', 'trace_indeterminate') "
                "LIMIT 1",
                (str(message.trace_id),),
            ).fetchone()
            accepted_current = self._connection.execute(
                "SELECT 1 FROM runtime_ledger WHERE fact_type = 'message_accepted' "
                "AND message_id = ? LIMIT 1",
                (str(message.message_id),),
            ).fetchone()
        if parent is None or parent["trace_id"] != str(message.trace_id):
            raise RuntimeRegistrationInvalid(
                "causation_id must identify an accepted message in the same trace"
            )
        if terminal is not None and accepted_current is None:
            raise RuntimeRegistrationInvalid("causal trace already has a terminal disposition")

    async def _request_local(
        self,
        message: RuntimeMessageEnvelope,
        timeout_seconds: float | None,
    ) -> RuntimeRequestOutcome:
        if message.kind is not RuntimeMessageKind.REQUEST:
            raise RuntimeRegistrationInvalid("request() requires a request envelope")
        _, recorded, pending = await self._accept_local(message)
        if recorded is not None:
            return recorded
        if pending is None:
            raise RuntimeRequestTimedOut(message.message_id)
        try:
            if timeout_seconds is None:
                return await asyncio.shield(pending)
            async with asyncio.timeout(timeout_seconds):
                return await asyncio.shield(pending)
        except TimeoutError as error:
            raise RuntimeRequestTimedOut(message.message_id) from error

    async def _playback_request_local(
        self, message: RuntimeMessageEnvelope
    ) -> RuntimeRequestOutcome:
        """Evaluate nested replay traffic without adding canonical business history."""
        session = _PLAYBACK_SESSION.get()
        registration = next(
            (
                item
                for item in self._registrations_by_key.values()
                if item.instance_id == message.target.instance_id
            ),
            None,
        )
        if (
            session is not None
            and registration is not None
            and registration.replay_authority is RuntimeReplayMode.EXTERNAL_EXCHANGE
        ):
            return self._recorded_external_playback(message, registration, session)
        target = self._validate_target(message)
        descriptor = next(
            action
            for action in target.adapter.describe().actions
            if action.action_id == message.action_id
        )
        if descriptor.replay_mode is RuntimeReplayMode.EXTERNAL_EXCHANGE:
            severity = _PLAYBACK_SEVERITY.get()
            if severity is not None:
                severity[0] = RuntimeTraceDisposition.INDETERMINATE
            raise RuntimeReplayIncompatible(
                f"playback cannot contact external action: {message.action_id}"
            )
        historical = (
            self._match_recorded_playback_request(message, session)
            if session is not None
            else None
        )
        dispatch_message = historical or message
        token = _CURRENT_ENVELOPE.set(dispatch_message)
        try:
            result = await target.adapter.dispatch(dispatch_message)
        except Exception as error:
            result = _runtime_fault_result(dispatch_message, error)
        finally:
            _CURRENT_ENVELOPE.reset(token)
        severity = _PLAYBACK_SEVERITY.get()
        if (
            severity is not None
            and result.trace_disposition is RuntimeTraceDisposition.INDETERMINATE
        ):
            severity[0] = RuntimeTraceDisposition.INDETERMINATE
        status = (
            RuntimeDeliveryStatus.COMPLETED
            if result.response.kind is RuntimeMessageKind.RESPONSE
            else RuntimeDeliveryStatus.FAULTED
        )
        receipt = RuntimeMessageReceipt(
            message_id=message.message_id,
            trace_id=message.trace_id,
            accepted_position=0,
            status=status,
        )
        return RuntimeRequestOutcome(
            request=receipt,
            response=result.response,
            terminal_position=0,
            trace_disposition=result.trace_disposition,
        )

    def _recorded_external_playback(
        self,
        message: RuntimeMessageEnvelope,
        registration: ComponentOccurrenceRegistration,
        session: _PlaybackSession,
    ) -> RuntimeRequestOutcome:
        boundary = session.external_boundaries.get(registration.instance_key)
        if boundary is None:
            self._mark_playback_indeterminate()
            raise RuntimeReplayIncompatible(
                f"external boundary has no reconstruction disposition: "
                f"{registration.instance_key}"
            )
        historical = self._match_recorded_playback_request(message, session)
        if historical is None:
            self._mark_playback_indeterminate()
            raise RuntimeReplayIncompatible(
                f"no recorded external exchange matches {registration.instance_key}: "
                f"{message.action_id}"
            )
        with self._db_lock:
            exchange = self._connection.execute(
                "SELECT runtime_position FROM runtime_ledger "
                "WHERE fact_type = 'external_exchange' AND message_id = ? "
                "AND runtime_position <= ? ORDER BY runtime_position LIMIT 1",
                (str(historical.message_id), session.through_position),
            ).fetchone()
            recorded = self._connection.execute(
                "SELECT * FROM runtime_messages WHERE message_id = ? "
                "AND terminal_position IS NOT NULL AND terminal_position <= ?",
                (str(historical.message_id), session.through_position),
            ).fetchone()
        if exchange is None or recorded is None or not recorded["response_json"]:
            self._mark_playback_indeterminate()
            raise RuntimeReplayIncompatible(
                f"recorded response is unavailable for external boundary "
                f"{registration.instance_key}: {message.action_id}"
            )
        response = _decode_envelope(json.loads(recorded["response_json"]))
        receipt = RuntimeMessageReceipt(
            message_id=historical.message_id,
            trace_id=historical.trace_id,
            accepted_position=int(recorded["accepted_position"]),
            status=RuntimeDeliveryStatus(str(recorded["status"])),
        )
        return RuntimeRequestOutcome(
            request=receipt,
            response=response,
            terminal_position=int(recorded["terminal_position"]),
            trace_disposition=RuntimeTraceDisposition(str(recorded["trace_disposition"])),
        )

    def _match_recorded_playback_request(
        self,
        message: RuntimeMessageEnvelope,
        session: _PlaybackSession,
    ) -> RuntimeMessageEnvelope | None:
        causation_clause = (
            "causation_id IS NULL" if message.causation_id is None else "causation_id = ?"
        )
        values: list[object] = [
            str(message.trace_id),
            str(message.target.instance_id),
            message.action_id,
            session.through_position,
        ]
        if message.causation_id is not None:
            values.append(str(message.causation_id))
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT * FROM runtime_ledger WHERE fact_type = 'message_accepted' "
                "AND trace_id = ? AND instance_id = ? AND action_id = ? "
                "AND runtime_position <= ? AND "
                + causation_clause
                + " ORDER BY runtime_position",
                tuple(values),
            ).fetchall()
        requested_signature = _playback_message_signature(message)
        for row in rows:
            message_id = UUID(str(row["message_id"]))
            if message_id in session.consumed_message_ids or not row["envelope_json"]:
                continue
            candidate = _decode_envelope(json.loads(row["envelope_json"]))
            if _playback_message_signature(candidate) != requested_signature:
                continue
            session.consumed_message_ids.add(message_id)
            return candidate
        return None

    @staticmethod
    def _mark_playback_indeterminate() -> None:
        severity = _PLAYBACK_SEVERITY.get()
        if severity is not None:
            severity[0] = RuntimeTraceDisposition.INDETERMINATE

    def _validate_target(self, message: RuntimeMessageEnvelope) -> _TargetState:
        if message.source.runtime_id != self.runtime_id:
            raise RuntimeAddressUnknown(
                f"non-local source runtime address: {message.source.runtime_id}"
            )
        if not any(
            registration.instance_id == message.source.instance_id
            for registration in self._registrations_by_key.values()
        ):
            raise RuntimeAddressUnknown(
                f"source occurrence is not registered: {message.source.instance_id}"
            )
        if message.target.runtime_id != self.runtime_id:
            raise RuntimeAddressUnknown(f"non-local runtime address: {message.target.runtime_id}")
        target = self._targets.get(message.target.instance_id)
        if target is None:
            raise RuntimeAddressUnknown(str(message.target.instance_id))
        if message.component_contract_id != target.registration.component_contract_id:
            raise RuntimeAddressUnknown("component contract does not match target occurrence")
        descriptors = {action.action_id: action for action in target.adapter.describe().actions}
        descriptor = descriptors.get(message.action_id)
        if descriptor is None:
            raise RuntimeActionUnknown(message.action_id)
        if message.schema_version != descriptor.schema_version:
            raise RuntimeSchemaUnsupported(f"{message.action_id}@{message.schema_version}")
        if message.payload.codec_id != descriptor.request_codec_id:
            raise RuntimeSchemaUnsupported(message.payload.codec_id)
        if message.payload.content_type != descriptor.request_content_type:
            raise RuntimeSchemaUnsupported(message.payload.content_type)
        if message.payload.codec_version != descriptor.request_codec_version:
            raise RuntimeSchemaUnsupported(
                f"{message.payload.codec_id}@{message.payload.codec_version}"
            )
        return target

    async def _worker(self, target: _TargetState) -> None:
        while True:
            delivery = await target.queue.get()
            try:
                await self._deliver(target, delivery)
            finally:
                target.queue.task_done()

    async def _deliver(self, target: _TargetState, delivery: _Delivery) -> None:
        message = delivery.envelope
        if self._health == "fail_stopped":
            self._fault_undelivered(
                delivery,
                RuntimeFailStopped(
                    "runtime entered fail-stop before this accepted delivery could start"
                ),
            )
            return
        descriptor = next(
            action
            for action in target.adapter.describe().actions
            if action.action_id == message.action_id
        )
        try:
            with self._db_lock, self._connection:
                self._insert_fact(
                    "delivery_started",
                    registration=target.registration,
                    envelope=message,
                    details={"attempt": 1},
                )
                self._connection.execute(
                    "UPDATE runtime_messages SET status = ? WHERE message_id = ?",
                    (RuntimeDeliveryStatus.DELIVERING.value, str(message.message_id)),
                )
        except sqlite3.Error as error:
            failure = self._enter_fail_stop(
                "delivery-start persistence failed before component execution: " f"{error}",
                envelope=message,
            )
            self._fault_undelivered(delivery, failure)
            return

        token = _CURRENT_ENVELOPE.set(message)
        try:
            result = await target.adapter.dispatch(message)
        except RuntimeTerminalEncodingFailed as error:
            failure = self._enter_fail_stop(
                f"terminal encoding failed after component execution: {error}",
                envelope=message,
            )
            self._fault_undelivered(delivery, failure)
            return
        except Exception as error:
            result = _runtime_fault_result(message, error)
        finally:
            _CURRENT_ENVELOPE.reset(token)

        if self._health == "fail_stopped":
            self._fault_undelivered(
                delivery,
                RuntimeFailStopped(
                    "runtime entered fail-stop while this delivery was in flight"
                ),
            )
            return

        disposition = result.trace_disposition
        status = (
            RuntimeDeliveryStatus.COMPLETED
            if result.response.kind is RuntimeMessageKind.RESPONSE
            else RuntimeDeliveryStatus.FAULTED
        )
        delivery_position: int | None = None
        finalized_trace: _FinalizedTrace | None = None
        try:
            with self._db_lock, self._connection:
                self._insert_fact(
                    "response_recorded"
                    if result.response.kind is RuntimeMessageKind.RESPONSE
                    else "fault_recorded",
                    registration=target.registration,
                    envelope=result.response,
                    details={"request_message_id": str(message.message_id)},
                )
                if result.canonical_effect is not None:
                    self._insert_fact(
                        "canonical_effect",
                        registration=target.registration,
                        envelope=message,
                        details={
                            "effect": result.canonical_effect,
                            "effect_digest": result.effect_digest,
                        },
                    )
                if descriptor.replay_mode is RuntimeReplayMode.EXTERNAL_EXCHANGE:
                    self._insert_fact(
                        "external_exchange",
                        registration=target.registration,
                        envelope=message,
                        details={
                            "response_message_id": str(result.response.message_id),
                            "playback_only": True,
                        },
                    )
                if message.causation_id is not None:
                    delivery_position = self._insert_fact(
                        "delivery_completed",
                        registration=target.registration,
                        envelope=message,
                    )
                self._connection.execute(
                    "UPDATE runtime_messages SET status = ?, terminal_position = ?, "
                    "response_json = ?, trace_disposition = ? WHERE message_id = ?",
                    (
                        (
                            status.value
                            if message.causation_id is not None
                            else RuntimeDeliveryStatus.DELIVERING.value
                        ),
                        delivery_position,
                        _canonical_json(_encode(result.response)),
                        disposition.value,
                        str(message.message_id),
                    ),
                )
                finalized_trace = self._finalize_trace_if_complete(message.trace_id)
        except Exception as error:
            failure = self._enter_fail_stop(
                f"terminal persistence failed after component execution: {error}",
                envelope=message,
            )
            self._fault_undelivered(delivery, failure)
            return

        if message.causation_id is None:
            if finalized_trace is not None:
                self._resolve_finalized_trace(finalized_trace)
            return

        assert delivery_position is not None
        outcome = RuntimeRequestOutcome(
            request=RuntimeMessageReceipt(
                message_id=delivery.receipt.message_id,
                trace_id=delivery.receipt.trace_id,
                accepted_position=delivery.receipt.accepted_position,
                status=status,
            ),
            response=result.response,
            terminal_position=delivery_position,
            trace_disposition=disposition,
        )
        if not delivery.outcome.done():
            delivery.outcome.set_result(outcome)
        self._pending.pop(message.message_id, None)
        if finalized_trace is not None:
            self._resolve_finalized_trace(finalized_trace)

    def _finalize_trace_if_complete(self, trace_id: UUID) -> _FinalizedTrace | None:
        rows = self._connection.execute(
            """
            SELECT accepted.message_id, accepted.causation_id, accepted.envelope_json,
                   delivery.accepted_position, delivery.status, delivery.response_json,
                   delivery.trace_disposition, delivery.terminal_position
            FROM runtime_ledger AS accepted
            JOIN runtime_messages AS delivery ON delivery.message_id = accepted.message_id
            WHERE accepted.fact_type = 'message_accepted' AND accepted.trace_id = ?
            ORDER BY accepted.runtime_position
            """,
            (str(trace_id),),
        ).fetchall()
        if not rows or any(row["response_json"] is None for row in rows):
            return None
        roots = [row for row in rows if row["causation_id"] is None]
        if len(roots) != 1:
            raise sqlite3.DatabaseError("a completed trace must contain exactly one root")
        root = roots[0]
        if root["terminal_position"] is not None:
            return None
        root_disposition = RuntimeTraceDisposition(str(root["trace_disposition"]))
        disposition = (
            RuntimeTraceDisposition.INDETERMINATE
            if any(
                row["trace_disposition"] == RuntimeTraceDisposition.INDETERMINATE.value
                for row in rows
            )
            else root_disposition
        )
        root_envelope = _decode_envelope(json.loads(str(root["envelope_json"])))
        root_response = _decode_envelope(json.loads(str(root["response_json"])))
        root_target = self._targets.get(root_envelope.target.instance_id)
        terminal_position = self._insert_fact(
            f"trace_{disposition.value}",
            registration=root_target.registration if root_target is not None else None,
            envelope=root_envelope,
            details={"root_message_id": str(root_envelope.message_id)},
        )
        if disposition is RuntimeTraceDisposition.INDETERMINATE:
            self._insert_fact(
                "runtime_recovery_required",
                details={
                    "reason": "indeterminate trace requires reconstruction",
                    "trace_id": str(trace_id),
                },
            )
        status = (
            RuntimeDeliveryStatus.COMPLETED
            if root_response.kind is RuntimeMessageKind.RESPONSE
            else RuntimeDeliveryStatus.FAULTED
        )
        self._connection.execute(
            "UPDATE runtime_messages SET status = ?, terminal_position = ?, "
            "trace_disposition = ? WHERE message_id = ?",
            (
                status.value,
                terminal_position,
                disposition.value,
                str(root_envelope.message_id),
            ),
        )
        return _FinalizedTrace(
            root_message_id=root_envelope.message_id,
            trace_id=trace_id,
            accepted_position=int(root["accepted_position"]),
            response=root_response,
            status=status,
            terminal_position=terminal_position,
            disposition=disposition,
        )

    def _resolve_finalized_trace(self, finalized: _FinalizedTrace) -> None:
        pending = self._pending.pop(finalized.root_message_id, None)
        self._release_recovery_root(finalized.root_message_id)
        if finalized.disposition is RuntimeTraceDisposition.INDETERMINATE:
            self._health = "recovery_required"
        if pending is None or pending.done():
            return
        pending.set_result(
            RuntimeRequestOutcome(
                request=RuntimeMessageReceipt(
                    message_id=finalized.root_message_id,
                    trace_id=finalized.trace_id,
                    accepted_position=finalized.accepted_position,
                    status=finalized.status,
                ),
                response=finalized.response,
                terminal_position=finalized.terminal_position,
                trace_disposition=finalized.disposition,
            )
        )

    def _release_recovery_root(self, message_id: UUID) -> None:
        if self._recovery_root_message_id == message_id:
            self._recovery_root_message_id = None

    def _enter_fail_stop(
        self,
        reason: str,
        *,
        envelope: RuntimeMessageEnvelope | None = None,
    ) -> RuntimeFailStopped:
        self._health = "fail_stopped"
        self._recovery_root_message_id = None
        failure = RuntimeFailStopped(reason)
        if envelope is not None:
            try:
                with self._db_lock, self._connection:
                    response = _runtime_fault_result(envelope, failure).response
                    terminal_position = self._insert_fact(
                        "trace_indeterminate",
                        envelope=envelope,
                        details={
                            "root_message_id": str(envelope.message_id),
                            "reason": reason,
                        },
                    )
                    self._connection.execute(
                        "UPDATE runtime_messages SET status = ?, terminal_position = ?, "
                        "response_json = ?, trace_disposition = ? WHERE message_id = ?",
                        (
                            RuntimeDeliveryStatus.FAULTED.value,
                            terminal_position,
                            _canonical_json(_encode(response)),
                            RuntimeTraceDisposition.INDETERMINATE.value,
                            str(envelope.message_id),
                        ),
                    )
            except Exception:
                # A failed ledger may be unable to persist even the fail-stop marker. The
                # in-memory gate still quiesces all accepted traffic, and restart recovery
                # marks every unconfirmed delivery indeterminate from confirmed history.
                pass
        for target in self._targets.values():
            while True:
                try:
                    queued = target.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    self._fault_undelivered(
                        queued,
                        RuntimeFailStopped(
                            "runtime fail-stop quiesced this accepted delivery before execution"
                        ),
                    )
                finally:
                    target.queue.task_done()
        for message_id, pending in tuple(self._pending.items()):
            if not pending.done():
                pending.set_exception(failure)
            self._pending.pop(message_id, None)
        return failure

    def _fault_undelivered(
        self,
        delivery: _Delivery,
        failure: RuntimeFailStopped,
    ) -> None:
        self._release_recovery_root(delivery.envelope.message_id)
        if not delivery.outcome.done():
            delivery.outcome.set_exception(failure)
        self._pending.pop(delivery.envelope.message_id, None)

    async def _query_history_local(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage:
        if query.limit < 1 or query.limit > 1000:
            raise ValueError("history limit must be between 1 and 1000")
        clauses = ["runtime_id = ?", "runtime_position > ?"]
        values: list[object] = [
            str(query.runtime_id or self.runtime_id),
            query.after_position or 0,
        ]
        filters: tuple[tuple[str, object | None], ...] = (
            ("runtime_position <= ?", query.through_position),
            ("recorded_at > ?", query.after_time),
            ("recorded_at <= ?", query.through_time),
            ("instance_key = ?", query.instance_key),
            ("instance_id = ?", str(query.instance_id) if query.instance_id else None),
            ("component_contract_id = ?", query.component_contract_id),
            ("message_id = ?", str(query.message_id) if query.message_id else None),
            ("trace_id = ?", str(query.trace_id) if query.trace_id else None),
            (
                "correlation_id = ?",
                str(query.correlation_id) if query.correlation_id else None,
            ),
            (
                "causation_id = ?",
                str(query.causation_id) if query.causation_id else None,
            ),
            ("action_id = ?", query.action_id),
            ("schema_version = ?", query.schema_version),
            ("fact_type = ?", query.fact_type),
            (
                "json_extract(envelope_json, '$.kind') = ?",
                query.message_kind.value if query.message_kind else None,
            ),
        )
        for clause, value in filters:
            if value is not None:
                clauses.append(clause)
                values.append(value)
        if query.delivery_status is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM runtime_messages AS delivery "
                "WHERE delivery.message_id = runtime_ledger.message_id "
                "AND delivery.status = ?)"
            )
            values.append(query.delivery_status.value)
        if query.trace_disposition is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM runtime_ledger AS trace_terminal "
                "WHERE trace_terminal.trace_id = runtime_ledger.trace_id "
                "AND trace_terminal.fact_type = ?)"
            )
            values.append(f"trace_{query.trace_disposition.value}")
        values.append(query.limit + 1)
        sql = (
            "SELECT * FROM runtime_ledger WHERE "
            + " AND ".join(clauses)
            + " ORDER BY runtime_position LIMIT ?"
        )
        with self._db_lock:
            rows = self._connection.execute(sql, tuple(values)).fetchall()
        has_more = len(rows) > query.limit
        selected = rows[: query.limit]
        facts = tuple(_fact_from_row(row) for row in selected)
        return RuntimeHistoryPage(
            facts=facts,
            next_position=facts[-1].runtime_position if has_more and facts else None,
        )

    async def _get_trace_local(self, trace_id: UUID) -> RuntimeCausalTrace:
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT * FROM runtime_ledger WHERE runtime_id = ? AND trace_id = ? "
                "ORDER BY runtime_position",
                (str(self.runtime_id), str(trace_id)),
            ).fetchall()
        facts = tuple(_fact_from_row(row) for row in rows)
        disposition = next(
            (
                RuntimeTraceDisposition(fact.fact_type.removeprefix("trace_"))
                for fact in reversed(facts)
                if fact.fact_type in {"trace_committed", "trace_aborted", "trace_indeterminate"}
            ),
            None,
        )
        return RuntimeCausalTrace(trace_id=trace_id, facts=facts, disposition=disposition)

    def _resolve_external_boundaries(
        self,
        through: int,
        requested: tuple[RuntimeExternalBoundaryDisposition, ...],
        external_rows: list[sqlite3.Row],
    ) -> tuple[RuntimeExternalBoundaryDisposition, ...]:
        requested_by_id: dict[str, RuntimeExternalBoundaryDisposition] = {}
        for boundary in requested:
            if (
                not boundary.boundary_id.strip()
                or boundary.boundary_id in requested_by_id
                or not isinstance(boundary.mode, RuntimeExternalBoundaryMode)
                or (boundary.limitation is not None and not boundary.limitation.strip())
            ):
                raise RuntimeReplayIncompatible(
                    "external boundary dispositions require unique non-empty identities, "
                    "typed modes, and non-empty limitations"
                )
            requested_by_id[boundary.boundary_id] = boundary

        known = {
            registration.instance_key: registration
            for registration in self._registrations_by_key.values()
            if registration.replay_authority is RuntimeReplayMode.EXTERNAL_EXCHANGE
        }
        unknown = set(requested_by_id) - set(known)
        if unknown:
            raise RuntimeReplayIncompatible(
                f"external boundary dispositions target unknown occurrences: {sorted(unknown)}"
            )
        for boundary in requested:
            registration = known[boundary.boundary_id]
            if (
                boundary.mode
                in {RuntimeExternalBoundaryMode.LIVE, RuntimeExternalBoundaryMode.SIMULATED}
                and registration.instance_id not in self._targets
            ):
                raise RuntimeReplayIncompatible(
                    f"external boundary {boundary.boundary_id} declares "
                    f"{boundary.mode.value} without an attached adapter"
                )

        recorded_by_key: dict[str, list[sqlite3.Row]] = {}
        for row in external_rows:
            key = str(row["instance_key"] or "")
            recorded_by_key.setdefault(key, []).append(row)
        result: list[RuntimeExternalBoundaryDisposition] = []
        for boundary_id in sorted(set(requested_by_id) | set(recorded_by_key)):
            selected = requested_by_id.get(boundary_id)
            if selected is None:
                if boundary_id in known:
                    selected = RuntimeExternalBoundaryDisposition(
                        boundary_id=boundary_id,
                        mode=RuntimeExternalBoundaryMode.PLAYBACK_ONLY,
                    )
                else:
                    selected = RuntimeExternalBoundaryDisposition(
                        boundary_id=boundary_id,
                        mode=RuntimeExternalBoundaryMode.UNAVAILABLE,
                        limitation="recorded boundary has no compatible occurrence registration",
                    )
            limitations = [selected.limitation] if selected.limitation is not None else []
            missing_responses = 0
            for row in recorded_by_key.get(boundary_id, []):
                with self._db_lock:
                    terminal = self._connection.execute(
                        "SELECT response_json FROM runtime_messages WHERE message_id = ? "
                        "AND terminal_position IS NOT NULL AND terminal_position <= ?",
                        (str(row["message_id"]), through),
                    ).fetchone()
                if terminal is None or not terminal["response_json"]:
                    missing_responses += 1
            if missing_responses:
                limitations.append(
                    f"{missing_responses} recorded exchanges lack a terminal response"
                )
            if (
                selected.mode is RuntimeExternalBoundaryMode.PLAYBACK_ONLY
                and boundary_id not in recorded_by_key
            ):
                limitations.append("no recorded exchange exists at or before the cursor")
            if (
                selected.mode is RuntimeExternalBoundaryMode.UNAVAILABLE
                and not limitations
            ):
                limitations.append("no collaborator is attached for continuation after the cursor")
            result.append(
                RuntimeExternalBoundaryDisposition(
                    boundary_id=selected.boundary_id,
                    mode=selected.mode,
                    limitation="; ".join(limitations) if limitations else None,
                )
            )
        return tuple(result)

    def _current_root_coordinator_is_only_pending_delivery(self) -> bool:
        """Allow only an explicitly authorized root to reconstruct through messaging."""
        current = _CURRENT_ENVELOPE.get()
        if (
            current is None
            or current.kind is not RuntimeMessageKind.REQUEST
            or current.causation_id is not None
            or set(self._pending) != {current.message_id}
        ):
            return False
        target = self._targets.get(current.target.instance_id)
        if target is None:
            return False
        descriptor = next(
            (
                action
                for action in target.adapter.describe().actions
                if action.action_id == current.action_id
            ),
            None,
        )
        return descriptor is not None and descriptor.recovery_authorized

    async def _reconstruct_local(
        self, request: RuntimeReconstructionRequest
    ) -> RuntimeReconstructionReport:
        self._ensure_healthy(allow_recovery=True, allow_branch_pending=True)
        if self._pending and not self._current_root_coordinator_is_only_pending_delivery():
            raise RuntimeReplayTargetNotPrepared(
                "reconstruction requires all live deliveries to reach a terminal outcome"
            )
        if request.source_runtime_id not in {None, self.runtime_id}:
            raise RuntimeReplayIncompatible(
                "cross-runtime replay requires an imported source ledger"
            )
        source_head = self.current_position
        through = source_head if request.through_position is None else request.through_position
        if through < 0 or through > source_head:
            raise RuntimeReplayIncompatible(
                f"reconstruction cursor is outside confirmed history: {through}"
            )
        operation_id = uuid4()
        pending_branch = self._pending_branch
        if pending_branch is not None and through != pending_branch.source_cursor:
            reason = (
                "branch-pending reconstruction must use its selected source cursor: "
                f"{pending_branch.source_cursor}"
            )
            await self._record_reconstruction_rejected(operation_id, through, reason)
            raise RuntimeReplayIncompatible(reason)
        historical_branch = request.through_position is not None and through < source_head
        source_runtime_id = request.source_runtime_id or self.runtime_id
        prior_health = self._health
        self._append_fact(
            "reconstruction_started",
            details={
                "operation_id": str(operation_id),
                "source_runtime_id": str(source_runtime_id),
                "through_position": through,
                "reset_targets": request.reset_targets,
                "external_boundaries": cast(JsonValue, _encode(request.external_boundaries)),
            },
        )
        self._health = "reconstructing"
        with self._db_lock:
            rows = self._connection.execute(
                """
                SELECT effect.* FROM runtime_ledger AS effect
                WHERE effect.fact_type = 'canonical_effect'
                  AND effect.runtime_position <= ?
                  AND 'trace_committed' = (
                    SELECT terminal.fact_type FROM runtime_ledger AS terminal
                    WHERE terminal.trace_id = effect.trace_id
                      AND terminal.fact_type IN (
                        'trace_committed', 'trace_aborted', 'trace_indeterminate'
                      )
                      AND terminal.runtime_position <= ?
                    ORDER BY terminal.runtime_position DESC
                    LIMIT 1
                  )
                ORDER BY effect.runtime_position
                """,
                (through, through),
            ).fetchall()
            external_rows = self._connection.execute(
                "SELECT * FROM runtime_ledger WHERE fact_type = 'external_exchange' "
                "AND runtime_position <= ? ORDER BY runtime_position",
                (through,),
            ).fetchall()
        rows, superseded_effects = _select_replay_effect_rows(rows)
        external_effects = len(external_rows)
        try:
            external_boundaries = self._resolve_external_boundaries(
                through, request.external_boundaries, external_rows
            )
        except Exception as error:
            await self._record_reconstruction_rejected(
                operation_id, through, f"{type(error).__name__}: {error}"
            )
            self._health = prior_health
            raise
        state_owners = tuple(
            registration
            for registration in self._registrations_by_key.values()
            if registration.replay_authority is RuntimeReplayMode.CANONICAL_EFFECT
        )
        targets_by_id = {
            registration.instance_id: self._targets[registration.instance_id]
            for registration in state_owners
            if registration.instance_id in self._targets
        }
        verification_targets_by_id: dict[UUID, _TargetState] = {}
        for instance_id, target in self._targets.items():
            if (await target.adapter.replay_state_status()).available:
                verification_targets_by_id[instance_id] = target
        missing_state_owners = tuple(
            registration
            for registration in state_owners
            if registration.instance_id not in self._targets
        )
        missing_state_owner_ids = {
            registration.instance_id for registration in missing_state_owners
        }

        checkpoint_references: dict[str, str] = {}
        for key, value in request.checkpoint_references.items():
            if not isinstance(value, str) or not value.strip():
                await self._record_reconstruction_rejected(
                    operation_id, through, f"invalid checkpoint reference for {key}"
                )
                self._health = prior_health
                raise RuntimeReplayIncompatible(
                    f"checkpoint reference for {key} must be a non-empty string"
                )
            checkpoint_references[key] = value
        unknown_checkpoint_targets = set(checkpoint_references) - {
            target.registration.instance_key for target in targets_by_id.values()
        }
        if unknown_checkpoint_targets:
            await self._record_reconstruction_rejected(
                operation_id,
                through,
                f"unknown checkpoint targets: {sorted(unknown_checkpoint_targets)}",
            )
            self._health = prior_health
            raise RuntimeReplayIncompatible(
                f"checkpoint references target unknown state owners: "
                f"{sorted(unknown_checkpoint_targets)}"
            )
        if request.checkpoint_reference is not None:
            if len(targets_by_id) != 1 or checkpoint_references:
                await self._record_reconstruction_rejected(
                    operation_id,
                    through,
                    "singular checkpoint requires exactly one replay target",
                )
                self._health = prior_health
                raise RuntimeReplayIncompatible(
                    "checkpoint_reference requires exactly one replay target; "
                    "use checkpoint_references for multiple occurrences"
                )
            only_target = next(iter(targets_by_id.values()))
            checkpoint_references[only_target.registration.instance_key] = (
                request.checkpoint_reference
            )

        prepared_cursors: dict[UUID, int] = {}
        try:
            for instance_id, target in targets_by_id.items():
                status = await target.adapter.replay_state_status()
                if not status.available:
                    raise RuntimeReplayTargetNotPrepared(
                        f"{target.registration.instance_key}: " + "; ".join(status.limitations)
                    )
                reference = checkpoint_references.get(target.registration.instance_key)
                if reference is not None and not status.empty and not request.reset_targets:
                    raise RuntimeReplayTargetNotPrepared(
                        f"checkpoint import target is not empty: {target.registration.instance_key}"
                    )
                if status.prepared and reference is None and not request.reset_targets:
                    if status.checkpoint_cursor < 0 or status.checkpoint_cursor > through:
                        raise RuntimeReplayTargetNotPrepared(
                            f"prepared cursor for {target.registration.instance_key} "
                            f"is outside reconstruction range: {status.checkpoint_cursor}"
                        )
                    actual_digest = await target.adapter.replay_state_digest()
                    if actual_digest != status.state_digest:
                        raise RuntimeReplayTargetNotPrepared(
                            f"prepared-state digest differs for {target.registration.instance_key}"
                        )
                    prepared_cursors[instance_id] = status.checkpoint_cursor
                elif not status.empty and not request.reset_targets:
                    raise RuntimeReplayTargetNotPrepared(
                        f"reconstruction target is not empty or confirmed: "
                        f"{target.registration.instance_key}"
                    )
        except Exception as error:
            await self._record_reconstruction_rejected(
                operation_id, through, f"{type(error).__name__}: {error}"
            )
            self._health = prior_health
            raise

        checkpoint_cursors: dict[UUID, int] = {}
        limitations: list[str] = []
        try:
            for instance_id, target in targets_by_id.items():
                status = await target.adapter.replay_state_status()
                reference = checkpoint_references.get(target.registration.instance_key)
                if reference is not None:
                    if not status.empty:
                        await target.adapter.reset_replay_state()
                    checkpoint_cursor = await target.adapter.import_replay_checkpoint(reference)
                    if checkpoint_cursor < 0 or checkpoint_cursor > through:
                        raise RuntimeReplayIncompatible(
                            f"checkpoint cursor for {target.registration.instance_key} "
                            f"is outside reconstruction range: {checkpoint_cursor}"
                        )
                    checkpoint_cursors[instance_id] = checkpoint_cursor
                elif instance_id in prepared_cursors:
                    checkpoint_cursors[instance_id] = prepared_cursors[instance_id]
                else:
                    if not status.empty:
                        await target.adapter.reset_replay_state()
                    checkpoint_cursors[instance_id] = 0
                prepared = await target.adapter.replay_state_status()
                if reference is not None:
                    if (
                        not prepared.available
                        or not prepared.prepared
                        or prepared.checkpoint_cursor != checkpoint_cursors[instance_id]
                        or prepared.state_digest is None
                    ):
                        raise RuntimeReplayTargetNotPrepared(
                            f"checkpoint import was not confirmed by "
                            f"{target.registration.instance_key}"
                        )
                    actual_digest = await target.adapter.replay_state_digest()
                    if actual_digest != prepared.state_digest:
                        raise RuntimeReplayTargetNotPrepared(
                            f"checkpoint digest differs for "
                            f"{target.registration.instance_key}"
                        )
                elif not prepared.available or not prepared.empty:
                    if instance_id not in prepared_cursors:
                        raise RuntimeReplayTargetNotPrepared(
                            f"adapter did not prepare reconstruction target: "
                            f"{target.registration.instance_key}"
                        )
                limitations.extend(prepared.limitations)
        except Exception as error:
            self._health = "recovery_required"
            await self._record_reconstruction_indeterminate(
                operation_id, through, f"target preparation failed: {type(error).__name__}: {error}"
            )
            raise

        applied = 0
        skipped = superseded_effects
        incompatible = len(missing_state_owners)
        start_position = min(checkpoint_cursors.values(), default=0)
        playback_session = _PlaybackSession(
            through_position=through,
            external_boundaries={item.boundary_id: item for item in external_boundaries},
            consumed_message_ids=set(),
        )
        limitations.extend(
            f"missing state-owning occurrence binding: {registration.instance_key}"
            for registration in missing_state_owners
        )
        for row in rows:
            instance_id = UUID(row["instance_id"])
            target = self._targets.get(instance_id)
            if target is None:
                if instance_id not in missing_state_owner_ids:
                    incompatible += 1
                    limitations.append(f"missing occurrence binding: {instance_id}")
                continue
            if int(row["runtime_position"]) <= checkpoint_cursors.get(instance_id, 0):
                skipped += 1
                continue
            details = json.loads(row["details_json"])
            effect = details.get("effect")
            if not isinstance(effect, dict):
                skipped += 1
                limitations.append(f"malformed effect at position {row['runtime_position']}")
                continue
            effect_digest = details.get("effect_digest")
            actual_effect_digest = hashlib.sha256(
                _canonical_json(cast(JsonValue, effect)).encode("utf-8")
            ).hexdigest()
            if effect_digest != actual_effect_digest:
                incompatible += 1
                limitations.append(
                    f"effect {row['runtime_position']} digest mismatch"
                )
                break
            if not row["envelope_json"]:
                incompatible += 1
                limitations.append(
                    f"effect {row['runtime_position']} has no canonical request envelope"
                )
                break
            recorded_envelope = _decode_envelope(json.loads(row["envelope_json"]))
            severity = [RuntimeTraceDisposition.COMMITTED]
            playback_token = _PLAYBACK_MODE.set(True)
            severity_token = _PLAYBACK_SEVERITY.set(severity)
            session_token = _PLAYBACK_SESSION.set(playback_session)
            envelope_token = _CURRENT_ENVELOPE.set(recorded_envelope)
            try:
                await target.adapter.apply_replay_effect(cast(JsonObject, effect))
                if severity[0] is not RuntimeTraceDisposition.COMMITTED:
                    raise RuntimeReplayIncompatible(
                        f"nested playback disposition is {severity[0].value}"
                    )
            except Exception as error:
                incompatible += 1
                limitations.append(
                    f"effect {row['runtime_position']} incompatible: "
                    f"{type(error).__name__}: {error}"
                )
                break
            finally:
                _CURRENT_ENVELOPE.reset(envelope_token)
                _PLAYBACK_SESSION.reset(session_token)
                _PLAYBACK_SEVERITY.reset(severity_token)
                _PLAYBACK_MODE.reset(playback_token)
            applied += 1
        state_digests: JsonObject = {}
        verification_issues: list[str] = []
        for target in verification_targets_by_id.values():
            try:
                verification_severity = [RuntimeTraceDisposition.COMMITTED]
                playback_token = _PLAYBACK_MODE.set(True)
                severity_token = _PLAYBACK_SEVERITY.set(verification_severity)
                session_token = _PLAYBACK_SESSION.set(None)
                envelope_token = _CURRENT_ENVELOPE.set(None)
                try:
                    digest = await target.adapter.replay_state_digest()
                    state_digests[target.registration.instance_key] = digest
                    target_issues = list(await target.adapter.verify_replay_state())
                    if verification_severity[0] is not RuntimeTraceDisposition.COMMITTED:
                        target_issues.append(
                            "derived replay verification produced an indeterminate nested call"
                        )
                finally:
                    _CURRENT_ENVELOPE.reset(envelope_token)
                    _PLAYBACK_SESSION.reset(session_token)
                    _PLAYBACK_SEVERITY.reset(severity_token)
                    _PLAYBACK_MODE.reset(playback_token)
                verification_issues.extend(target_issues)
                limitations.extend(target_issues)
            except Exception as error:
                incompatible += 1
                limitations.append(
                    f"state verification failed for {target.registration.instance_key}: "
                    f"{type(error).__name__}: {error}"
                )
        if external_effects:
            limitations.append(
                f"{external_effects} external outbound effects were not repeated; "
                "recorded responses remained available for playback"
            )
        verified = incompatible == 0 and not verification_issues
        verified_digest = _state_digests_digest(state_digests) if verified else None
        report = RuntimeReconstructionReport(
            start_position=start_position,
            through_position=through,
            applied_effects=applied,
            skipped_effects=skipped,
            incompatible_effects=incompatible,
            state_digests=state_digests,
            limitations=tuple(limitations),
            external_effects_skipped=external_effects,
            external_boundaries=external_boundaries,
            verified=verified,
            verified_digest=verified_digest,
        )
        fact_type = "reconstruction_completed" if verified else "reconstruction_indeterminate"
        terminal_details: JsonObject = {
            "operation_id": str(operation_id),
            "start_position": start_position,
            "through_position": through,
            "applied_effects": applied,
            "skipped_effects": skipped,
            "incompatible_effects": incompatible,
            "external_effects_skipped": external_effects,
            "external_boundaries": cast(JsonValue, _encode(external_boundaries)),
            "state_digests": state_digests,
            "verified": verified,
            "verified_digest": verified_digest,
            "branch_provenance_required": verified and historical_branch,
        }
        try:
            with self._db_lock, self._connection:
                self._insert_fact(fact_type, details=terminal_details)
                if verified and historical_branch:
                    assert verified_digest is not None
                    self._insert_fact(
                        "branch_provenance_required",
                        details={
                            "source_runtime_id": str(source_runtime_id),
                            "source_cursor": through,
                            "verified_digest": verified_digest,
                            "state_digests": state_digests,
                        },
                    )
        except sqlite3.Error as error:
            self._health = "fail_stopped"
            raise RuntimeFailStopped(
                "reconstruction terminal persistence failed after state changes"
            ) from error
        if verified and historical_branch:
            assert verified_digest is not None
            self._pending_branch = _PendingBranch(
                source_runtime_id=source_runtime_id,
                source_cursor=through,
                verified_digest=verified_digest,
                state_digests=state_digests,
            )
            self._health = "branch_pending"
        else:
            self._health = "ready" if verified else "recovery_required"
        return report

    async def _record_reconstruction_rejected(
        self, operation_id: UUID, through: int, reason: str
    ) -> None:
        try:
            self._append_fact(
                "reconstruction_rejected",
                details={
                    "operation_id": str(operation_id),
                    "through_position": through,
                    "reason": reason,
                },
            )
        except RuntimeLedgerUnavailable as error:
            self._health = "fail_stopped"
            raise RuntimeFailStopped(
                "reconstruction rejection could not be durably recorded"
            ) from error

    async def _record_reconstruction_indeterminate(
        self, operation_id: UUID, through: int, reason: str
    ) -> None:
        try:
            self._append_fact(
                "reconstruction_indeterminate",
                details={
                    "operation_id": str(operation_id),
                    "through_position": through,
                    "reason": reason,
                },
            )
        except RuntimeLedgerUnavailable as error:
            self._health = "fail_stopped"
            raise RuntimeFailStopped(
                "reconstruction failure could not be durably recorded"
            ) from error

    async def _close_local(self) -> None:
        if self._health in {"closed", "closing"}:
            return
        self._health = "closing"
        self._recovery_root_message_id = None
        for target in self._targets.values():
            for worker in target.workers:
                worker.cancel()
        workers = [worker for target in self._targets.values() for worker in target.workers]
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        try:
            self._append_fact("runtime_shutdown", details={"runtime_key": self.runtime_key})
        finally:
            self._health = "closed"

    def _ensure_healthy(
        self,
        *,
        allow_recovery: bool = False,
        allow_branch_pending: bool = False,
    ) -> None:
        if self._health == "fail_stopped":
            raise RuntimeFailStopped("runtime is fail-stopped and requires reconstruction")
        allowed = {"ready", "starting"}
        if allow_recovery:
            allowed.add("recovery_required")
        if allow_branch_pending:
            allowed.add("branch_pending")
        if self._health not in allowed:
            raise RuntimeFailStopped(f"runtime is not accepting traffic: {self._health}")

    def _append_fact(
        self,
        fact_type: str,
        *,
        registration: ComponentOccurrenceRegistration | None = None,
        envelope: RuntimeMessageEnvelope | None = None,
        details: JsonObject | None = None,
    ) -> int:
        try:
            with self._db_lock, self._connection:
                return self._insert_fact(
                    fact_type,
                    registration=registration,
                    envelope=envelope,
                    details=details,
                )
        except sqlite3.Error as error:
            raise RuntimeLedgerUnavailable(str(error)) from error

    def _insert_fact(
        self,
        fact_type: str,
        *,
        registration: ComponentOccurrenceRegistration | None = None,
        envelope: RuntimeMessageEnvelope | None = None,
        message_id: UUID | None = None,
        trace_id: UUID | None = None,
        details: JsonObject | None = None,
    ) -> int:
        if fact_type in self._fail_next_fact_types:
            self._fail_next_fact_types.remove(fact_type)
            raise sqlite3.OperationalError(f"simulated ledger failure: {fact_type}")
        cursor = self._connection.execute(
            "INSERT INTO runtime_ledger(fact_type, recorded_at, runtime_id, instance_key, "
            "instance_id, component_contract_id, message_id, trace_id, correlation_id, "
            "causation_id, action_id, schema_version, details_json, envelope_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fact_type,
                _now(),
                str(self.runtime_id),
                registration.instance_key if registration else None,
                str(registration.instance_id)
                if registration
                else (str(envelope.target.instance_id) if envelope else None),
                registration.component_contract_id
                if registration
                else (envelope.component_contract_id if envelope else None),
                str(envelope.message_id if envelope else message_id)
                if envelope or message_id
                else None,
                str(envelope.trace_id if envelope else trace_id) if envelope or trace_id else None,
                str(envelope.correlation_id) if envelope and envelope.correlation_id else None,
                str(envelope.causation_id) if envelope and envelope.causation_id else None,
                envelope.action_id if envelope else None,
                envelope.schema_version if envelope else None,
                _canonical_json(details or {}),
                _canonical_json(_encode(envelope)) if envelope else None,
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.DatabaseError("runtime ledger insert returned no position")
        return int(cursor.lastrowid)


def _validate_registration(registration: ComponentOccurrenceRegistration) -> None:
    if not registration.instance_key.strip():
        raise RuntimeRegistrationInvalid("instance_key must be non-empty")
    if not registration.component_contract_id.startswith(("component.", "application.")):
        raise RuntimeRegistrationInvalid(
            "component_contract_id must be a stable component or application ID"
        )
    if not registration.binding_id.strip() or registration.binding_version < 1:
        raise RuntimeRegistrationInvalid("binding identity and positive version are required")
    if registration.queue_capacity < 1 or registration.max_in_flight < 1:
        raise RuntimeRegistrationInvalid("queue and concurrency bounds must be positive")
    if len(set(registration.configuration_references)) != len(
        registration.configuration_references
    ) or any(not reference.strip() for reference in registration.configuration_references):
        raise RuntimeRegistrationInvalid("configuration references must be non-empty and unique")


def _validate_declaration(declaration: ComponentOccurrenceDeclaration) -> None:
    _validate_registration(
        ComponentOccurrenceRegistration(
            instance_key=declaration.instance_key,
            instance_id=UUID(int=0),
            component_contract_id=declaration.component_contract_id,
            binding_id=declaration.binding_id,
            binding_version=declaration.binding_version,
            queue_capacity=declaration.queue_capacity,
            max_in_flight=declaration.max_in_flight,
            replay_authority=declaration.replay_authority,
            configuration_references=declaration.configuration_references,
        )
    )


def _validate_static_topology_manifest(
    manifest: RuntimeTopologyManifest, *, runtime_key: str
) -> None:
    if manifest.runtime_key != runtime_key:
        raise RuntimeRegistrationInvalid(
            f"manifest runtime_key differs: {manifest.runtime_key!r}"
        )
    if manifest.manifest_schema_version < 1:
        raise RuntimeRegistrationInvalid("manifest_schema_version must be positive")
    if len(manifest.manifest_hash) != 64 or any(
        character not in "0123456789abcdef" for character in manifest.manifest_hash
    ):
        raise RuntimeRegistrationInvalid("manifest_hash must be a lowercase SHA-256 digest")
    for declaration in manifest.occurrences:
        _validate_declaration(declaration)
    declared_keys = {item.instance_key for item in manifest.occurrences}
    if not declared_keys or len(declared_keys) != len(manifest.occurrences):
        raise RuntimeRegistrationInvalid("static occurrence keys must be non-empty and unique")
    operation_ids = {operation.operation_id for operation in manifest.curated_operations}
    if len(operation_ids) != len(manifest.curated_operations):
        raise RuntimeRegistrationInvalid("curated operation identities must be unique")
    declarations_by_key = {item.instance_key: item for item in manifest.occurrences}
    for operation in manifest.curated_operations:
        if (
            not operation.operation_id.strip()
            or operation.target_instance_key not in declared_keys
            or not operation.component_contract_id.strip()
            or not operation.action_id.strip()
            or operation.schema_version < 1
        ):
            raise RuntimeRegistrationInvalid(
                f"invalid curated operation declaration: {operation.operation_id}"
            )
        if (
            operation.component_contract_id
            != declarations_by_key[operation.target_instance_key].component_contract_id
        ):
            raise RuntimeRegistrationInvalid(
                f"curated operation contract differs from target: {operation.operation_id}"
            )


def _static_topology_plan(manifest: RuntimeTopologyManifest) -> JsonObject:
    return {
        "runtime_key": manifest.runtime_key,
        "manifest_schema_version": manifest.manifest_schema_version,
        "occurrences": [
            cast(JsonValue, _encode(declaration))
            for declaration in sorted(
                manifest.occurrences, key=lambda item: item.instance_key
            )
        ],
        "curated_operations": [
            cast(JsonValue, _encode(operation))
            for operation in sorted(
                manifest.curated_operations, key=lambda item: item.operation_id
            )
        ],
    }


def _topology_plan_hash(plan: JsonObject) -> str:
    return hashlib.sha256(_canonical_json(plan).encode("utf-8")).hexdigest()


def _topology_plan_declarations(
    encoded_plan: str,
) -> dict[str, ComponentOccurrenceDeclaration]:
    try:
        plan = json.loads(encoded_plan)
        occurrences = plan["occurrences"]
        if not isinstance(occurrences, list):
            raise TypeError("occurrences must be a list")
        declarations = {
            str(item["instance_key"]): ComponentOccurrenceDeclaration(
                instance_key=str(item["instance_key"]),
                component_contract_id=str(item["component_contract_id"]),
                binding_id=str(item["binding_id"]),
                binding_version=int(item["binding_version"]),
                queue_capacity=int(item["queue_capacity"]),
                max_in_flight=int(item["max_in_flight"]),
                replay_authority=RuntimeReplayMode(str(item["replay_authority"])),
                configuration_references=tuple(
                    str(reference) for reference in item["configuration_references"]
                ),
            )
            for item in occurrences
            if isinstance(item, dict)
        }
        if len(declarations) != len(occurrences):
            raise TypeError("occurrence declarations must be unique objects")
        return declarations
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeRegistrationInvalid(
            "durable static topology plan is malformed"
        ) from error


def _declaration_from_registration(
    registration: ComponentOccurrenceRegistration,
) -> ComponentOccurrenceDeclaration:
    return ComponentOccurrenceDeclaration(
        instance_key=registration.instance_key,
        component_contract_id=registration.component_contract_id,
        binding_id=registration.binding_id,
        binding_version=registration.binding_version,
        queue_capacity=registration.queue_capacity,
        max_in_flight=registration.max_in_flight,
        replay_authority=registration.replay_authority,
        configuration_references=registration.configuration_references,
    )


def _binding_replay_authority(
    actions: tuple[RuntimeActionBindingDescriptor, ...],
) -> RuntimeReplayMode:
    modes = {action.replay_mode for action in actions}
    for mode in (
        RuntimeReplayMode.EXTERNAL_EXCHANGE,
        RuntimeReplayMode.CANONICAL_EFFECT,
        RuntimeReplayMode.COORDINATOR_TRACE,
    ):
        if mode in modes:
            return mode
    return RuntimeReplayMode.NO_STATE_EFFECT


def _validate_adapter_concurrency(
    actions: tuple[RuntimeActionBindingDescriptor, ...], max_in_flight: int
) -> None:
    incompatible = [action.action_id for action in actions if max_in_flight > action.max_in_flight]
    if incompatible:
        raise RuntimeRegistrationInvalid(
            "registration concurrency exceeds action binding policy: "
            f"max_in_flight={max_in_flight}, actions={incompatible}"
        )


def _registration_from_row(row: sqlite3.Row) -> ComponentOccurrenceRegistration:
    return ComponentOccurrenceRegistration(
        instance_key=row["instance_key"],
        instance_id=UUID(row["instance_id"]),
        component_contract_id=row["component_contract_id"],
        binding_id=row["binding_id"],
        binding_version=int(row["binding_version"]),
        queue_capacity=int(row["queue_capacity"]),
        max_in_flight=int(row["max_in_flight"]),
        replay_authority=RuntimeReplayMode(row["replay_authority"]),
        configuration_references=tuple(
            str(value) for value in json.loads(row["configuration_references_json"])
        ),
    )


def _fact_from_row(row: sqlite3.Row) -> RuntimeLedgerFact:
    return RuntimeLedgerFact(
        runtime_position=int(row["runtime_position"]),
        fact_type=row["fact_type"],
        recorded_at=row["recorded_at"],
        runtime_id=UUID(row["runtime_id"]),
        instance_key=row["instance_key"],
        instance_id=UUID(row["instance_id"]) if row["instance_id"] else None,
        component_contract_id=row["component_contract_id"],
        message_id=UUID(row["message_id"]) if row["message_id"] else None,
        trace_id=UUID(row["trace_id"]) if row["trace_id"] else None,
        correlation_id=UUID(row["correlation_id"]) if row["correlation_id"] else None,
        causation_id=UUID(row["causation_id"]) if row["causation_id"] else None,
        action_id=row["action_id"],
        schema_version=int(row["schema_version"]) if row["schema_version"] else None,
        details=cast(JsonObject, json.loads(row["details_json"])),
        envelope=(
            _decode_envelope(json.loads(row["envelope_json"])) if row["envelope_json"] else None
        ),
    )


def _select_replay_effect_rows(
    rows: list[sqlite3.Row],
) -> tuple[list[sqlite3.Row], int]:
    """Let the latest aggregate effect in a committed trace replace its derived effects."""
    superseding_positions: dict[str, int] = {}
    for row in rows:
        details = json.loads(str(row["details_json"]))
        effect = details.get("effect") if isinstance(details, dict) else None
        payload = effect.get("payload") if isinstance(effect, dict) else None
        if isinstance(payload, dict) and payload.get("supersedes_trace_effects") is True:
            superseding_positions[str(row["trace_id"])] = int(row["runtime_position"])
    if not superseding_positions:
        return rows, 0
    selected = [
        row
        for row in rows
        if str(row["trace_id"]) not in superseding_positions
        or int(row["runtime_position"]) == superseding_positions[str(row["trace_id"])]
    ]
    return selected, len(rows) - len(selected)


def _runtime_fault_result(
    request: RuntimeMessageEnvelope, error: Exception
) -> RuntimeDispatchResult:
    response = RuntimeMessageEnvelope(
        message_id=uuid4(),
        kind=RuntimeMessageKind.FAULT,
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
            codec_id="runtime.fault.json",
            codec_version=1,
            value={"type": type(error).__name__, "message": str(error)},
        ),
    )
    return RuntimeDispatchResult(
        response=response,
        trace_disposition=RuntimeTraceDisposition.INDETERMINATE,
    )


def _encode(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return cast(str, value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _encode(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_encode(item) for item in value]
    raise TypeError(f"not JSON encodable: {type(value).__name__}")


def _require_canonical_json_value(value: object, *, path: str) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise RuntimeSchemaUnsupported(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_canonical_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RuntimeSchemaUnsupported(
                    f"{path} contains a non-string object key"
                )
            _require_canonical_json_value(item, path=f"{path}.{key}")
        return
    raise RuntimeSchemaUnsupported(
        f"{path} must contain only canonical JSON values, not {type(value).__name__}"
    )


def _decode_envelope(data: object) -> RuntimeMessageEnvelope:
    if not isinstance(data, dict):
        raise ValueError("envelope must be an object")
    source = cast(dict[str, object], data["source"])
    target = cast(dict[str, object], data["target"])
    payload = cast(dict[str, object], data["payload"])
    return RuntimeMessageEnvelope(
        message_id=UUID(str(data["message_id"])),
        kind=RuntimeMessageKind(str(data["kind"])),
        source=RuntimeAddress(UUID(str(source["runtime_id"])), UUID(str(source["instance_id"]))),
        target=RuntimeAddress(UUID(str(target["runtime_id"])), UUID(str(target["instance_id"]))),
        component_contract_id=str(data["component_contract_id"]),
        action_id=str(data["action_id"]),
        schema_version=int(cast(int | str, data["schema_version"])),
        trace_id=UUID(str(data["trace_id"])),
        correlation_id=UUID(str(data["correlation_id"])) if data.get("correlation_id") else None,
        causation_id=UUID(str(data["causation_id"])) if data.get("causation_id") else None,
        idempotency_key=str(data["idempotency_key"]) if data.get("idempotency_key") else None,
        created_at=str(data["created_at"]),
        payload=RuntimePayload(
            content_type=str(payload["content_type"]),
            codec_id=str(payload["codec_id"]),
            codec_version=int(cast(int | str, payload["codec_version"])),
            value=cast(JsonValue, payload["value"]),
        ),
    )


def _playback_message_signature(message: RuntimeMessageEnvelope) -> str:
    """Match a derived playback call to its original durable request, excluding new identity."""
    return _canonical_json(
        {
            "kind": message.kind.value,
            "source": cast(JsonValue, _encode(message.source)),
            "target": cast(JsonValue, _encode(message.target)),
            "component_contract_id": message.component_contract_id,
            "action_id": message.action_id,
            "schema_version": message.schema_version,
            "correlation_id": (
                str(message.correlation_id) if message.correlation_id is not None else None
            ),
            "causation_id": str(message.causation_id) if message.causation_id is not None else None,
            "idempotency_key": message.idempotency_key,
            "payload": cast(JsonValue, _encode(message.payload)),
        }
    )


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _state_digests_digest(state_digests: JsonObject) -> str:
    return hashlib.sha256(_canonical_json(state_digests).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
