from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import zlib
from collections.abc import Callable, Coroutine
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid4, uuid5

from components.runtime.message_runtime.protocol import (
    RuntimeActionUnknown,
    RuntimeAddressUnknown,
    RuntimeCausalTrace,
    RuntimeFailStopped,
    RuntimeLedgerUnavailable,
    RuntimeRegistrationInvalid,
    RuntimeReplayIncompatible,
    RuntimeReplayTargetNotPrepared,
    RuntimeSchemaUnsupported,
    RuntimeTraceSummary,
    RuntimeTraceSummaryPage,
)
from components.runtime.messaging import (
    ActionRef,
    ComponentOccurrenceDeclaration,
    ComponentOccurrenceRegistration,
    JsonObject,
    JsonValue,
    RuntimeActionBindingDescriptor,
    RuntimeAddress,
    RuntimeCanonicalEffectReference,
    RuntimeConsistencyAccess,
    RuntimeDeliveryStatus,
    RuntimeDeliveryUnknown,
    RuntimeExternalBoundaryDisposition,
    RuntimeExternalBoundaryMode,
    RuntimeHealth,
    RuntimeHistoryPage,
    RuntimeHistoryQuery,
    RuntimeLaneDeclaration,
    RuntimeLedgerFact,
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
    RuntimeReplayMode,
    RuntimeStorageVersionUnsupported,
    RuntimeTopologyConfirmation,
    RuntimeTopologyManifest,
    RuntimeTraceDisposition,
    topology_manifest_hash,
)

_STORAGE_SCHEMA_VERSION = 4
_RESPONSE_LANE = "__responses__"


class _ManagedParticipant(RuntimeParticipant, Protocol):
    async def apply_replay_effect(self, effect: JsonObject) -> None: ...

    async def replay_state_status(self) -> object: ...

    async def reset_replay_state(self) -> None: ...

    async def import_replay_checkpoint(self, reference: str) -> int: ...

    async def replay_state_digest(self) -> str: ...

    async def verify_replay_state(self) -> tuple[str, ...]: ...


@dataclass(slots=True)
class _Delivery:
    envelope: RuntimeMessageEnvelope
    receipt: RuntimeMessageReceipt


@dataclass(slots=True)
class _LaneState:
    declaration: RuntimeLaneDeclaration
    queue: asyncio.Queue[_Delivery]
    workers: list[asyncio.Task[None]]


@dataclass(slots=True)
class _ConsistencyState:
    condition: asyncio.Condition
    readers: int = 0
    writer: bool = False
    waiting_writers: int = 0


@dataclass(slots=True)
class _TargetState:
    registration: ComponentOccurrenceRegistration
    participant: _ManagedParticipant
    actions: dict[str, RuntimeActionBindingDescriptor]
    lanes: dict[str, _LaneState]
    consistency: dict[str, _ConsistencyState]


@dataclass(frozen=True, slots=True)
class _PendingBranch:
    source_runtime_id: UUID
    source_cursor: int
    verified_digest: str
    state_digests: JsonObject


class _AdmissionLease:
    def __init__(
        self,
        state: _ConsistencyState | None,
        access: RuntimeConsistencyAccess,
    ) -> None:
        self._state = state
        self._access = access

    async def __aenter__(self) -> None:
        state = self._state
        if state is None:
            return
        async with state.condition:
            if self._access is RuntimeConsistencyAccess.SHARED:
                await state.condition.wait_for(
                    lambda: not state.writer and state.waiting_writers == 0
                )
                state.readers += 1
                return
            state.waiting_writers += 1
            try:
                await state.condition.wait_for(lambda: not state.writer and state.readers == 0)
                state.writer = True
            finally:
                state.waiting_writers -= 1

    async def __aexit__(self, *_: object) -> None:
        state = self._state
        if state is None:
            return
        async with state.condition:
            if self._access is RuntimeConsistencyAccess.SHARED:
                state.readers -= 1
            else:
                state.writer = False
            state.condition.notify_all()


class _ParticipantContext(RuntimeParticipantContext):
    def __init__(self, runtime: SqliteMessageRuntime, envelope: RuntimeMessageEnvelope) -> None:
        self._runtime = runtime
        self._envelope = envelope

    async def send(
        self,
        action: ActionRef,
        arguments: JsonObject,
        *,
        target: RuntimeAddress,
        kind: RuntimeMessageKind = RuntimeMessageKind.REQUEST,
        message_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> RuntimeMessageReceipt:
        if kind not in {RuntimeMessageKind.REQUEST, RuntimeMessageKind.SIGNAL}:
            raise RuntimeRegistrationInvalid("participants may send only requests or signals")
        parent = self._envelope
        child = RuntimeMessageEnvelope(
            message_id=message_id or uuid4(),
            kind=kind,
            source=parent.target,
            target=target,
            component_contract_id=action.component_contract_id,
            action_id=action.action_id,
            schema_version=action.schema_version,
            trace_id=parent.trace_id,
            correlation_id=parent.correlation_id or parent.message_id,
            causation_id=parent.message_id,
            idempotency_key=idempotency_key,
            created_at=_now(),
            payload=RuntimePayload(
                codec_id=action.request_codec_id,
                codec_version=action.request_codec_version,
                content_type=action.request_content_type,
                value=arguments,
            ),
        )
        return await self._runtime._accept(child)

    async def complete(
        self,
        request_message_id: UUID,
        result: RuntimePayload,
        *,
        trace_disposition: RuntimeTraceDisposition = RuntimeTraceDisposition.COMMITTED,
        canonical_effect: JsonObject | None = None,
        effect_digest: str | None = None,
    ) -> RuntimeMessageReceipt:
        return await self._runtime._complete(
            self._envelope,
            request_message_id,
            RuntimeMessageKind.RESPONSE,
            result,
            trace_disposition,
            canonical_effect,
            effect_digest,
        )

    async def fault(
        self,
        request_message_id: UUID,
        error: RuntimePayload,
        *,
        trace_disposition: RuntimeTraceDisposition,
        canonical_effect: JsonObject | None = None,
        effect_digest: str | None = None,
    ) -> RuntimeMessageReceipt:
        return await self._runtime._complete(
            self._envelope,
            request_message_id,
            RuntimeMessageKind.FAULT,
            error,
            trace_disposition,
            canonical_effect,
            effect_digest,
        )

    async def ack(
        self,
        message_id: UUID,
        *,
        canonical_effect: JsonObject | None = None,
        effect_digest: str | None = None,
    ) -> RuntimeMessageReceipt:
        return await self._runtime._ack(
            self._envelope,
            message_id,
            canonical_effect,
            effect_digest,
        )

    async def canonical_effect_reference(
        self, request_message_id: UUID
    ) -> RuntimeCanonicalEffectReference:
        return self._runtime._canonical_effect_reference(
            request_message_id,
            expected_trace_id=self._envelope.trace_id,
            expected_ancestor_id=self._envelope.message_id,
        )

    def address_for(self, instance_key: str) -> RuntimeAddress:
        return self._runtime.address_for(instance_key)


class SqliteMessageRuntime:
    """Local message runtime with one durable chronology and uniform delivery."""

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
        path = Path(database_path)
        if path != Path(":memory:"):
            parent_created = not path.parent.exists()
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if parent_created:
                path.parent.chmod(0o700)
        self._database_path = str(path)
        self._db_lock = threading.RLock()
        self._connection = sqlite3.connect(self._database_path, check_same_thread=False)
        if path != Path(":memory:"):
            path.chmod(0o600)
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema(runtime_key, runtime_id)
        self.runtime_id = UUID(self._metadata("runtime_id"))
        self._health = RuntimeHealth.STARTING
        self._targets: dict[UUID, _TargetState] = {}
        self._registrations_by_key: dict[str, ComponentOccurrenceRegistration] = {}
        self._manifest: RuntimeTopologyManifest | None = None
        self._recovery_root: UUID | None = None
        self._recovery_result_health: RuntimeHealth | None = None
        self._pending_branch = self._load_pending_branch()
        self._fail_next_fact_types: set[str] = set()
        self._active_deliveries: dict[
            UUID, tuple[asyncio.Task[None], RuntimeMessageEnvelope]
        ] = {}
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name=f"bibliotek-runtime-{runtime_key}",
            daemon=True,
        )
        self._loop_thread.start()
        self._load_registrations()
        self._run_initialization()

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
    def health(self) -> RuntimeHealth:
        return self._health

    def address_for(self, instance_key: str) -> RuntimeAddress:
        registration = self._registrations_by_key.get(instance_key)
        if registration is None:
            raise RuntimeAddressUnknown(instance_key)
        return RuntimeAddress(self.runtime_id, registration.instance_id)

    async def current_position(self) -> int:
        return await self._on_runtime(self._current_position())

    async def prepare_static_topology(self, manifest: RuntimeTopologyManifest) -> None:
        await self._on_runtime(self._prepare_static_topology(manifest))

    async def register_occurrence(
        self, declaration: ComponentOccurrenceDeclaration
    ) -> ComponentOccurrenceRegistration:
        return await self._on_runtime(self._register_occurrence(declaration))

    async def attach_participant(
        self,
        registration: ComponentOccurrenceRegistration,
        participant: RuntimeParticipant,
        actions: tuple[RuntimeActionBindingDescriptor, ...] = (),
    ) -> None:
        await self._on_runtime(
            self._attach_participant(
                registration,
                cast(_ManagedParticipant, participant),
                actions,
            )
        )

    async def confirm_static_topology(
        self, manifest: RuntimeTopologyManifest
    ) -> RuntimeTopologyConfirmation:
        return await self._on_runtime(self._confirm_static_topology(manifest))

    async def send(self, message: RuntimeMessageEnvelope) -> RuntimeMessageReceipt:
        return await self._on_runtime(self._accept(message))

    async def query_history(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage:
        return await self._on_runtime(self._query_history(query))

    async def count_history(self, query: RuntimeHistoryQuery) -> int:
        return await self._on_runtime(self._count_history(query))

    async def query_trace_summaries(
        self,
        *,
        after_position: int | None = None,
        limit: int = 100,
        newest_first: bool = False,
        root_action_ids: tuple[str, ...] = (),
    ) -> RuntimeTraceSummaryPage:
        return await self._on_runtime(
            self._query_trace_summaries(
                after_position=after_position,
                limit=limit,
                newest_first=newest_first,
                root_action_ids=root_action_ids,
            )
        )

    async def get_trace(
        self, trace_id: UUID, *, include_payload: bool = False
    ) -> RuntimeCausalTrace:
        return await self._on_runtime(self._get_trace(trace_id, include_payload=include_payload))

    async def get_envelope(self, message_id: UUID) -> RuntimeMessageEnvelope | None:
        return await self._on_runtime(self._get_envelope(message_id))

    async def lookup_message_outcome(
        self, message_id: UUID
    ) -> RuntimeMessageOutcome | None:
        return await self._on_runtime(self._lookup_message_outcome(message_id))

    async def reconstruct(
        self, request: RuntimeReconstructionRequest
    ) -> RuntimeReconstructionReport:
        return await self._on_runtime(self._reconstruct(request))

    async def record_branch_provenance(
        self,
        *,
        source_runtime_id: UUID,
        source_cursor: int,
        verified_digest: str,
    ) -> int:
        return await self._on_runtime(
            self._record_branch_provenance(source_runtime_id, source_cursor, verified_digest)
        )

    async def aclose(self) -> None:
        if self._health is RuntimeHealth.CLOSED:
            return
        await self._on_runtime(self._close())
        self._loop.call_soon_threadsafe(self._loop.stop)
        await asyncio.to_thread(self._loop_thread.join, 5)
        with self._db_lock:
            self._connection.close()
        self._health = RuntimeHealth.CLOSED

    async def __aenter__(self) -> SqliteMessageRuntime:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def simulate_ledger_failure_once(self, fact_type: str) -> None:
        self._fail_next_fact_types.add(fact_type)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _on_runtime(self, coroutine: Coroutine[object, object, Any]) -> Any:
        if asyncio.get_running_loop() is self._loop:
            return await coroutine
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return await asyncio.wrap_future(future)

    def _run_initialization(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self._initialize_runtime(), self._loop)
        future.result()

    async def _initialize_runtime(self) -> None:
        recovered = self._recover_incomplete_deliveries()
        with self._db_lock:
            effects = self._connection.execute(
                "SELECT 1 FROM runtime_ledger WHERE fact_type = 'canonical_effect' LIMIT 1"
            ).fetchone()
        if self._pending_branch is not None:
            initial_health = RuntimeHealth.BRANCH_PENDING
        elif recovered or effects is not None:
            initial_health = RuntimeHealth.RECOVERY_REQUIRED
        else:
            initial_health = RuntimeHealth.STARTING
        if initial_health is not self._health:
            self._transition_health(initial_health, "runtime initialization")
        self._append_fact("runtime_initialized", details={"health": self._health.value})

    async def _current_position(self) -> int:
        with self._db_lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(runtime_position), 0) AS position FROM runtime_ledger"
            ).fetchone()
        return int(row["position"])

    async def _prepare_static_topology(self, manifest: RuntimeTopologyManifest) -> None:
        self._ensure_not_closed()
        if manifest.runtime_key != self.runtime_key:
            raise RuntimeRegistrationInvalid("manifest runtime key differs")
        if manifest.manifest_schema_version < 4:
            raise RuntimeRegistrationInvalid("message-native manifests require schema version 4")
        normalized = _canonical_json(_encode(manifest))
        digest = topology_manifest_hash(manifest)
        if digest != manifest.manifest_hash:
            raise RuntimeRegistrationInvalid("manifest hash differs from canonical content")
        with self._db_lock, self._connection:
            row = self._connection.execute(
                "SELECT manifest_hash, manifest_json FROM runtime_topology WHERE singleton = 1"
            ).fetchone()
            if row is not None and (
                row["manifest_hash"] != manifest.manifest_hash or row["manifest_json"] != normalized
            ):
                raise RuntimeRegistrationInvalid(
                    "static topology is already prepared with different content"
                )
            if row is None:
                self._connection.execute(
                    "INSERT INTO runtime_topology"
                    "(singleton, manifest_hash, manifest_json, confirmed) "
                    "VALUES (1, ?, ?, 0)",
                    (manifest.manifest_hash, normalized),
                )
                self._insert_fact(
                    "topology_prepared",
                    details={"manifest_hash": manifest.manifest_hash},
                )
        self._manifest = manifest

    async def _register_occurrence(
        self, declaration: ComponentOccurrenceDeclaration
    ) -> ComponentOccurrenceRegistration:
        if self._manifest is None:
            self._manifest = self._load_manifest()
        if self._manifest is None or declaration not in self._manifest.occurrences:
            raise RuntimeRegistrationInvalid("occurrence is not in the prepared topology")
        _validate_declaration(declaration)
        existing = self._registrations_by_key.get(declaration.instance_key)
        if existing is not None:
            if _registration_matches(existing, declaration):
                return existing
            raise RuntimeRegistrationInvalid(
                f"durable occurrence differs: {declaration.instance_key}"
            )
        registration = ComponentOccurrenceRegistration(
            instance_key=declaration.instance_key,
            instance_id=uuid4(),
            component_contract_id=declaration.component_contract_id,
            binding_id=declaration.binding_id,
            binding_version=declaration.binding_version,
            lanes=declaration.lanes,
            replay_authority=declaration.replay_authority,
            configuration_references=declaration.configuration_references,
        )
        try:
            with self._db_lock, self._connection:
                self._connection.execute(
                    "INSERT INTO runtime_occurrences(instance_key, instance_id, "
                    "component_contract_id, binding_id, binding_version, lanes_json, "
                    "replay_authority, configuration_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        registration.instance_key,
                        str(registration.instance_id),
                        registration.component_contract_id,
                        registration.binding_id,
                        registration.binding_version,
                        _canonical_json(_encode(registration.lanes)),
                        registration.replay_authority.value,
                        _canonical_json(list(registration.configuration_references)),
                    ),
                )
                self._insert_fact(
                    "occurrence_registered",
                    registration=registration,
                    details={"binding_id": registration.binding_id},
                )
        except sqlite3.IntegrityError as error:
            raise RuntimeRegistrationInvalid(str(error)) from error
        self._registrations_by_key[registration.instance_key] = registration
        return registration

    async def _attach_participant(
        self,
        registration: ComponentOccurrenceRegistration,
        participant: _ManagedParticipant,
        actions: tuple[RuntimeActionBindingDescriptor, ...],
    ) -> None:
        durable = self._registrations_by_key.get(registration.instance_key)
        if durable != registration:
            raise RuntimeRegistrationInvalid(
                "attachment registration differs from durable identity"
            )
        if registration.instance_id in self._targets:
            raise RuntimeRegistrationInvalid("occurrence already has an attached participant")
        action_map: dict[str, RuntimeActionBindingDescriptor] = {}
        lane_names = {lane.name for lane in registration.lanes}
        for descriptor in actions:
            if descriptor.component_contract_id != registration.component_contract_id:
                raise RuntimeRegistrationInvalid("action contract differs from occurrence")
            if descriptor.binding_id != registration.binding_id:
                raise RuntimeRegistrationInvalid("action binding differs from occurrence")
            if descriptor.binding_version != registration.binding_version:
                raise RuntimeRegistrationInvalid("action binding version differs")
            if descriptor.concurrency_lane not in lane_names:
                raise RuntimeRegistrationInvalid(
                    f"action lane is undeclared: {descriptor.concurrency_lane}"
                )
            if descriptor.action_id in action_map:
                raise RuntimeRegistrationInvalid(f"duplicate action: {descriptor.action_id}")
            action_map[descriptor.action_id] = descriptor
        lanes: dict[str, _LaneState] = {}
        target = _TargetState(registration, participant, action_map, lanes, {})
        for declaration in registration.lanes:
            queue: asyncio.Queue[_Delivery] = asyncio.Queue(declaration.queue_capacity)
            lane = _LaneState(declaration, queue, [])
            lanes[declaration.name] = lane
            lane.workers.extend(
                asyncio.create_task(self._worker(target, lane))
                for _ in range(declaration.worker_limit)
            )
        response_declaration = RuntimeLaneDeclaration(_RESPONSE_LANE, 0, 1)
        response_lane = _LaneState(response_declaration, asyncio.Queue(), [])
        lanes[_RESPONSE_LANE] = response_lane
        response_lane.workers.append(asyncio.create_task(self._worker(target, response_lane)))
        self._targets[registration.instance_id] = target
        self._append_fact("occurrence_ready", registration=registration)

    async def _confirm_static_topology(
        self, manifest: RuntimeTopologyManifest
    ) -> RuntimeTopologyConfirmation:
        if self._manifest is None:
            self._manifest = self._load_manifest()
        if self._manifest != manifest:
            raise RuntimeRegistrationInvalid("confirmation differs from prepared topology")
        expected = {item.instance_key for item in manifest.occurrences}
        if set(self._registrations_by_key) != expected:
            raise RuntimeRegistrationInvalid("not every declared occurrence is registered")
        if {item.registration.instance_key for item in self._targets.values()} != expected:
            raise RuntimeRegistrationInvalid("not every occurrence has an attached participant")
        operation_ids: set[str] = set()
        for operation in manifest.curated_operations:
            if operation.operation_id in operation_ids:
                raise RuntimeRegistrationInvalid(
                    f"duplicate curated operation: {operation.operation_id}"
                )
            operation_ids.add(operation.operation_id)
            registration = self._registrations_by_key.get(operation.target_instance_key)
            if registration is None:
                raise RuntimeRegistrationInvalid(
                    f"curated operation target is unknown: {operation.target_instance_key}"
                )
            if registration.component_contract_id != operation.component_contract_id:
                raise RuntimeRegistrationInvalid(
                    f"curated operation contract differs: {operation.operation_id}"
                )
            target = self._targets.get(registration.instance_id)
            descriptor = target.actions.get(operation.action_id) if target is not None else None
            if descriptor is None or descriptor.schema_version != operation.schema_version:
                raise RuntimeRegistrationInvalid(
                    f"curated operation action is unavailable: {operation.operation_id}"
                )
            comparisons = {
                "binding_id": descriptor.binding_id,
                "binding_version": descriptor.binding_version,
                "request_codec_id": descriptor.request_codec_id,
                "request_codec_version": descriptor.request_codec_version,
                "request_payload_disposition": descriptor.request_payload_disposition,
                "result_payload_disposition": descriptor.result_payload_disposition,
                "fault_payload_disposition": descriptor.fault_payload_disposition,
                "effect_payload_disposition": descriptor.effect_payload_disposition,
            }
            for name, actual in comparisons.items():
                expected_value = getattr(operation, name)
                if expected_value != actual:
                    raise RuntimeRegistrationInvalid(
                        f"curated operation {name} differs: {operation.operation_id}"
                    )
        topology_hash = _topology_hash(manifest)
        with self._db_lock, self._connection:
            self._connection.execute(
                "UPDATE runtime_topology SET confirmed = 1, topology_hash = ? WHERE singleton = 1",
                (topology_hash,),
            )
            self._insert_fact(
                "topology_confirmed",
                details={
                    "manifest_hash": manifest.manifest_hash,
                    "topology_hash": topology_hash,
                },
            )
        if self._health is RuntimeHealth.STARTING:
            self._transition_health(RuntimeHealth.READY, "static topology confirmed")
        return RuntimeTopologyConfirmation(
            manifest_hash=manifest.manifest_hash,
            topology_hash=topology_hash,
            occurrence_count=len(expected),
        )

    async def _accept(self, message: RuntimeMessageEnvelope) -> RuntimeMessageReceipt:
        try:
            _require_json(message.payload.value)
            canonical = _canonical_json(_encode(message))
            message = _decode_envelope(json.loads(canonical))
        except Exception as error:
            self._record_rejection(message, error)
            raise
        envelope_hash = hashlib.sha256(canonical.encode()).hexdigest()
        with self._db_lock:
            existing = self._connection.execute(
                "SELECT * FROM runtime_messages WHERE message_id = ?",
                (str(message.message_id),),
            ).fetchone()
        if existing is not None:
            if existing["envelope_hash"] != envelope_hash:
                self._record_rejection(message, RuntimeMessageConflict(str(message.message_id)))
                raise RuntimeMessageConflict(str(message.message_id))
            return _receipt_from_row(message, existing)

        target, descriptor = self._validate_message(message)
        recovery_root = (
            message.kind is RuntimeMessageKind.REQUEST
            and message.causation_id is None
            and descriptor is not None
            and descriptor.recovery_authorized
        )
        self._validate_causality(message)
        self._ensure_ingress(message, recovery_root)
        if recovery_root:
            if self._recovery_root not in {None, message.message_id}:
                raise RuntimeFailStopped("another recovery root is active")
            self._recovery_root = message.message_id
        lane_name = (
            _RESPONSE_LANE
            if message.kind in {RuntimeMessageKind.RESPONSE, RuntimeMessageKind.FAULT}
            else cast(RuntimeActionBindingDescriptor, descriptor).concurrency_lane
        )
        lane = target.lanes[lane_name]
        if lane.queue.full():
            self._record_rejection(message, RuntimeQueueFull(lane_name))
            raise RuntimeQueueFull(lane_name)
        try:
            with self._db_lock, self._connection:
                position = self._insert_message(message, target.registration, envelope_hash)
        except sqlite3.Error as error:
            raise RuntimeLedgerUnavailable(str(error)) from error
        receipt = RuntimeMessageReceipt(
            message_id=message.message_id,
            trace_id=message.trace_id,
            accepted_position=position,
            status=RuntimeDeliveryStatus.ACCEPTED,
        )
        lane.queue.put_nowait(_Delivery(message, receipt))
        return receipt

    def _canonical_effect_reference(
        self,
        request_message_id: UUID,
        *,
        expected_trace_id: UUID,
        expected_ancestor_id: UUID,
    ) -> RuntimeCanonicalEffectReference:
        with self._db_lock:
            row = self._connection.execute(
                "SELECT runtime_position, trace_id, causation_id, details_json "
                "FROM runtime_ledger WHERE fact_type = 'canonical_effect' "
                "AND message_id = ? ORDER BY runtime_position DESC LIMIT 1",
                (str(request_message_id),),
            ).fetchone()
            message = self._connection.execute(
                "SELECT status, trace_id, causation_id FROM runtime_messages WHERE message_id = ?",
                (str(request_message_id),),
            ).fetchone()
        if row is None or message is None:
            raise RuntimeReplayIncompatible(
                f"completed step has no canonical effect: {request_message_id}"
            )
        if UUID(str(row["trace_id"])) != expected_trace_id:
            raise RuntimeReplayIncompatible("canonical effect belongs to another trace")
        if message["status"] not in {
            RuntimeDeliveryStatus.COMPLETED.value,
            RuntimeDeliveryStatus.FAULTED.value,
        }:
            raise RuntimeReplayIncompatible("canonical effect step is not terminal")
        if not self._is_causal_descendant(request_message_id, expected_ancestor_id):
            raise RuntimeReplayIncompatible("canonical effect is not a causal descendant")
        details = json.loads(str(row["details_json"]))
        digest = details.get("effect_digest")
        if not isinstance(digest, str) or not digest:
            raise RuntimeReplayIncompatible("canonical effect digest is unavailable")
        return RuntimeCanonicalEffectReference(request_message_id, digest)

    def _is_causal_descendant(self, message_id: UUID, ancestor_id: UUID) -> bool:
        current: UUID | None = message_id
        seen: set[UUID] = set()
        with self._db_lock:
            while current is not None and current not in seen:
                if current == ancestor_id:
                    return True
                seen.add(current)
                row = self._connection.execute(
                    "SELECT causation_id FROM runtime_messages WHERE message_id = ?",
                    (str(current),),
                ).fetchone()
                if row is None or row["causation_id"] is None:
                    return False
                current = UUID(str(row["causation_id"]))
        return False

    async def _complete(
        self,
        envelope: RuntimeMessageEnvelope,
        request_message_id: UUID,
        response_kind: RuntimeMessageKind,
        payload: RuntimePayload,
        disposition: RuntimeTraceDisposition,
        canonical_effect: JsonObject | None,
        effect_digest: str | None,
    ) -> RuntimeMessageReceipt:
        if self._health is RuntimeHealth.FAIL_STOPPED:
            raise RuntimeFailStopped("runtime is fail-stopped")
        if (
            envelope.kind is not RuntimeMessageKind.REQUEST
            or request_message_id != envelope.message_id
        ):
            raise RuntimeDeliveryUnknown(str(request_message_id))
        with self._db_lock:
            row = self._connection.execute(
                "SELECT status FROM runtime_messages WHERE message_id = ?",
                (str(request_message_id),),
            ).fetchone()
        if row is None or row["status"] != RuntimeDeliveryStatus.DELIVERING.value:
            raise RuntimeDeliveryUnknown(str(request_message_id))
        response = RuntimeMessageEnvelope(
            message_id=uuid5(request_message_id, response_kind.value),
            kind=response_kind,
            source=envelope.target,
            target=envelope.source,
            component_contract_id=envelope.component_contract_id,
            action_id=envelope.action_id,
            schema_version=envelope.schema_version,
            trace_id=envelope.trace_id,
            correlation_id=request_message_id,
            causation_id=request_message_id,
            created_at=_now(),
            payload=payload,
        )
        canonical = _canonical_json(_encode(response))
        envelope_hash = hashlib.sha256(canonical.encode()).hexdigest()
        target, _ = self._validate_message(response)
        try:
            with self._db_lock, self._connection:
                accepted_position = self._insert_message(
                    response, target.registration, envelope_hash
                )
                if canonical_effect is not None:
                    effect_payload_hash = self._store_json_payload(
                        canonical_effect,
                        content_type="application/json",
                        codec_id="codec.runtime.canonical-effect.json",
                        codec_version=1,
                    )
                    self._insert_fact(
                        "canonical_effect",
                        registration=self._targets[envelope.target.instance_id].registration,
                        envelope=envelope,
                        details={
                            "effect_payload_hash": effect_payload_hash,
                            "effect_digest": effect_digest,
                        },
                    )
                descriptor = self._targets[envelope.target.instance_id].actions.get(
                    envelope.action_id
                )
                if (
                    descriptor is not None
                    and descriptor.replay_mode is RuntimeReplayMode.EXTERNAL_EXCHANGE
                ):
                    self._insert_fact(
                        "external_exchange",
                        registration=self._targets[envelope.target.instance_id].registration,
                        envelope=envelope,
                        details={"response_message_id": str(response.message_id)},
                    )
                delivery_position = self._insert_fact(
                    "delivery_completed",
                    registration=self._targets[envelope.target.instance_id].registration,
                    envelope=envelope,
                    details={"response_message_id": str(response.message_id)},
                )
                self._connection.execute(
                    "UPDATE runtime_messages SET status = ?, terminal_position = ?, "
                    "trace_disposition = ? WHERE message_id = ?",
                    (
                        RuntimeDeliveryStatus.COMPLETED.value
                        if response_kind is RuntimeMessageKind.RESPONSE
                        else RuntimeDeliveryStatus.FAULTED.value,
                        delivery_position,
                        disposition.value,
                        str(request_message_id),
                    ),
                )
        except Exception as error:
            await self._enter_fail_stop(
                f"terminal persistence failed after component effect: {error}", envelope
            )
            raise RuntimeFailStopped(str(error)) from error
        receipt = RuntimeMessageReceipt(
            response.message_id,
            response.trace_id,
            accepted_position,
            RuntimeDeliveryStatus.ACCEPTED,
        )
        target.lanes[_RESPONSE_LANE].queue.put_nowait(_Delivery(response, receipt))
        return receipt

    async def _ack(
        self,
        envelope: RuntimeMessageEnvelope,
        message_id: UUID,
        canonical_effect: JsonObject | None,
        effect_digest: str | None,
    ) -> RuntimeMessageReceipt:
        if self._health is RuntimeHealth.FAIL_STOPPED:
            raise RuntimeFailStopped("runtime is fail-stopped")
        if message_id != envelope.message_id or envelope.kind is RuntimeMessageKind.REQUEST:
            raise RuntimeDeliveryUnknown(str(message_id))
        with self._db_lock:
            row = self._connection.execute(
                "SELECT * FROM runtime_messages WHERE message_id = ?",
                (str(message_id),),
            ).fetchone()
        if row is None or row["status"] != RuntimeDeliveryStatus.DELIVERING.value:
            raise RuntimeDeliveryUnknown(str(message_id))
        try:
            with self._db_lock, self._connection:
                if canonical_effect is not None:
                    effect_payload_hash = self._store_json_payload(
                        canonical_effect,
                        content_type="application/json",
                        codec_id="codec.runtime.canonical-effect.json",
                        codec_version=1,
                    )
                    target = self._targets[envelope.target.instance_id]
                    self._insert_fact(
                        "canonical_effect",
                        registration=target.registration,
                        envelope=envelope,
                        details={
                            "effect_payload_hash": effect_payload_hash,
                            "effect_digest": effect_digest,
                        },
                    )
                terminal_position = self._insert_fact(
                    "delivery_completed",
                    registration=self._targets[envelope.target.instance_id].registration,
                    envelope=envelope,
                )
                self._connection.execute(
                    "UPDATE runtime_messages SET status = ?, terminal_position = ?, "
                    "trace_disposition = ? WHERE message_id = ?",
                    (
                        RuntimeDeliveryStatus.COMPLETED.value,
                        terminal_position,
                        RuntimeTraceDisposition.COMMITTED.value,
                        str(message_id),
                    ),
                )
                trace_terminal = self._finalize_trace(envelope.trace_id)
        except Exception as error:
            await self._enter_fail_stop(f"ack persistence failed: {error}", envelope)
            raise RuntimeFailStopped(str(error)) from error
        if trace_terminal is not None:
            terminal_position, disposition = trace_terminal
        else:
            disposition = RuntimeTraceDisposition.COMMITTED
        return RuntimeMessageReceipt(
            message_id=message_id,
            trace_id=envelope.trace_id,
            accepted_position=int(row["accepted_position"]),
            status=RuntimeDeliveryStatus.COMPLETED,
            terminal_position=terminal_position,
            trace_disposition=disposition,
        )

    async def _worker(self, target: _TargetState, lane: _LaneState) -> None:
        while True:
            delivery = await lane.queue.get()
            task = asyncio.create_task(self._deliver(target, delivery))
            self._active_deliveries[delivery.envelope.message_id] = (
                task,
                delivery.envelope,
            )
            try:
                await task
            except asyncio.CancelledError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise
            finally:
                self._active_deliveries.pop(delivery.envelope.message_id, None)
                lane.queue.task_done()

    async def _deliver(self, target: _TargetState, delivery: _Delivery) -> None:
        envelope = delivery.envelope
        if self._health is RuntimeHealth.FAIL_STOPPED:
            await self._mark_indeterminate(envelope, "runtime fail-stop quiesced delivery")
            return
        descriptor = target.actions.get(envelope.action_id)
        access = (
            RuntimeConsistencyAccess.INDEPENDENT
            if descriptor is None
            or envelope.kind in {RuntimeMessageKind.RESPONSE, RuntimeMessageKind.FAULT}
            else descriptor.consistency_access
        )
        group = descriptor.consistency_group if descriptor is not None else None
        state = None
        if group is not None:
            state = target.consistency.setdefault(group, _ConsistencyState(asyncio.Condition()))
        async with _AdmissionLease(state, access):
            try:
                with self._db_lock, self._connection:
                    self._insert_fact(
                        "delivery_started",
                        registration=target.registration,
                        envelope=envelope,
                        details={"attempt": 1},
                    )
                    self._connection.execute(
                        "UPDATE runtime_messages SET status = ? WHERE message_id = ?",
                        (RuntimeDeliveryStatus.DELIVERING.value, str(envelope.message_id)),
                    )
            except sqlite3.Error as error:
                await self._enter_fail_stop(
                    f"delivery-start persistence failed: {error}", envelope
                )
                return
            try:
                participant_task = asyncio.create_task(
                    target.participant.deliver(
                        envelope,
                        _ParticipantContext(self, envelope),
                    )
                )
                deadline = (
                    descriptor.deadline_seconds
                    if descriptor is not None and envelope.kind is RuntimeMessageKind.REQUEST
                    else None
                )
                try:
                    if deadline is None:
                        await participant_task
                    else:
                        await asyncio.wait_for(asyncio.shield(participant_task), deadline)
                except TimeoutError:
                    try:
                        self._transition_health(
                            RuntimeHealth.QUIESCING,
                            f"action deadline expired: {envelope.action_id}",
                        )
                    except Exception as error:
                        await self._enter_fail_stop(
                            f"deadline transition persistence failed: {error}", envelope
                        )
                        return
                    participant_task.cancel()
                    await asyncio.gather(participant_task, return_exceptions=True)
                except asyncio.CancelledError:
                    participant_task.cancel()
                    await asyncio.gather(participant_task, return_exceptions=True)
                    raise
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if self._health is RuntimeHealth.FAIL_STOPPED:
                    return
                if envelope.kind is RuntimeMessageKind.REQUEST:
                    await self._runtime_fault(envelope, error)
                else:
                    await self._mark_indeterminate(envelope, str(error))
                return
            with self._db_lock:
                row = self._connection.execute(
                    "SELECT status FROM runtime_messages WHERE message_id = ?",
                    (str(envelope.message_id),),
                ).fetchone()
            if row is not None and row["status"] == RuntimeDeliveryStatus.DELIVERING.value:
                await self._mark_indeterminate(
                    envelope, "participant returned without completing delivery"
                )

    async def _runtime_fault(self, envelope: RuntimeMessageEnvelope, error: Exception) -> None:
        payload = RuntimePayload(
            codec_id="codec.runtime.failure.json",
            codec_version=1,
            value={
                "type": type(error).__name__,
                "message": str(error),
                "evidence": {},
            },
        )
        try:
            await self._complete(
                envelope,
                envelope.message_id,
                RuntimeMessageKind.FAULT,
                payload,
                RuntimeTraceDisposition.INDETERMINATE,
                None,
                None,
            )
        except Exception:
            await self._mark_indeterminate(envelope, str(error))

    async def _mark_indeterminate(self, envelope: RuntimeMessageEnvelope, reason: str) -> None:
        try:
            with self._db_lock, self._connection:
                position = self._insert_fact(
                    "delivery_indeterminate",
                    registration=self._targets[envelope.target.instance_id].registration,
                    envelope=envelope,
                    details={"reason": reason},
                )
                self._connection.execute(
                    "UPDATE runtime_messages SET status = ?, terminal_position = ?, "
                    "trace_disposition = ? WHERE message_id = ?",
                    (
                        RuntimeDeliveryStatus.INDETERMINATE.value,
                        position,
                        RuntimeTraceDisposition.INDETERMINATE.value,
                        str(envelope.message_id),
                    ),
                )
                self._finalize_trace(envelope.trace_id)
        except Exception:
            self._health = RuntimeHealth.FAIL_STOPPED
        if self._health is not RuntimeHealth.FAIL_STOPPED:
            self._transition_health(
                RuntimeHealth.RECOVERY_REQUIRED,
                f"delivery indeterminate: {reason}",
            )

    def _validate_message(
        self, message: RuntimeMessageEnvelope
    ) -> tuple[_TargetState, RuntimeActionBindingDescriptor | None]:
        if message.source.runtime_id != self.runtime_id:
            raise RuntimeAddressUnknown("source runtime is not local")
        if message.target.runtime_id != self.runtime_id:
            raise RuntimeAddressUnknown("target runtime is not local")
        if not any(
            item.instance_id == message.source.instance_id
            for item in self._registrations_by_key.values()
        ):
            raise RuntimeAddressUnknown("source occurrence is not registered")
        target = self._targets.get(message.target.instance_id)
        if target is None:
            raise RuntimeAddressUnknown("target occurrence is not attached")
        if message.kind in {RuntimeMessageKind.RESPONSE, RuntimeMessageKind.FAULT}:
            self._validate_response(message)
            return target, None
        if message.component_contract_id != target.registration.component_contract_id:
            raise RuntimeAddressUnknown("component contract differs from target")
        descriptor = target.actions.get(message.action_id)
        if descriptor is None:
            raise RuntimeActionUnknown(message.action_id)
        if message.schema_version != descriptor.schema_version:
            raise RuntimeSchemaUnsupported(f"{message.action_id}@{message.schema_version}")
        if (
            message.payload.codec_id != descriptor.request_codec_id
            or message.payload.codec_version != descriptor.request_codec_version
            or message.payload.content_type != descriptor.request_content_type
        ):
            raise RuntimeSchemaUnsupported(message.payload.codec_id)
        return target, descriptor

    def _validate_response(self, message: RuntimeMessageEnvelope) -> None:
        if message.correlation_id is None or message.causation_id != message.correlation_id:
            raise RuntimeRegistrationInvalid("response requires matching correlation and causation")
        with self._db_lock:
            row = self._connection.execute(
                "SELECT message_id FROM runtime_messages WHERE message_id = ?",
                (str(message.correlation_id),),
            ).fetchone()
        if row is None:
            raise RuntimeRegistrationInvalid("response request is unknown")
        request = self._load_envelope(UUID(str(row["message_id"])))
        if request.kind is not RuntimeMessageKind.REQUEST:
            raise RuntimeRegistrationInvalid("response correlation is not a request")
        if (
            message.source != request.target
            or message.target != request.source
            or message.trace_id != request.trace_id
            or message.action_id != request.action_id
            or message.component_contract_id != request.component_contract_id
            or message.schema_version != request.schema_version
        ):
            raise RuntimeRegistrationInvalid("response does not match its request")

    def _validate_causality(self, message: RuntimeMessageEnvelope) -> None:
        with self._db_lock:
            terminal = self._connection.execute(
                "SELECT 1 FROM runtime_ledger WHERE trace_id = ? AND fact_type IN "
                "('trace_committed', 'trace_aborted', 'trace_indeterminate') LIMIT 1",
                (str(message.trace_id),),
            ).fetchone()
            if terminal is not None:
                raise RuntimeRegistrationInvalid("trace is already terminal")
            if message.causation_id is None:
                root = self._connection.execute(
                    "SELECT 1 FROM runtime_messages WHERE trace_id = ? AND causation_id IS NULL",
                    (str(message.trace_id),),
                ).fetchone()
                if root is not None:
                    raise RuntimeRegistrationInvalid("trace already has a root")
                if message.kind not in {RuntimeMessageKind.REQUEST, RuntimeMessageKind.SIGNAL}:
                    raise RuntimeRegistrationInvalid("response cannot be a trace root")
                return
            parent = self._connection.execute(
                "SELECT trace_id FROM runtime_messages WHERE message_id = ?",
                (str(message.causation_id),),
            ).fetchone()
        if parent is None or parent["trace_id"] != str(message.trace_id):
            raise RuntimeRegistrationInvalid("causation must reference the same open trace")

    def _ensure_ingress(
        self, message: RuntimeMessageEnvelope, recovery_root: bool
    ) -> None:
        if self._health is RuntimeHealth.READY:
            return
        if self._health is RuntimeHealth.QUIESCING and message.causation_id is not None:
            return
        if self._health is RuntimeHealth.RECOVERY_REQUIRED:
            if recovery_root:
                return
            if self._recovery_root is not None and message.causation_id is not None:
                return
        raise RuntimeFailStopped(f"runtime health is {self._health}")

    def _ensure_not_closed(self) -> None:
        if self._health in {RuntimeHealth.CLOSED, RuntimeHealth.FAIL_STOPPED}:
            raise RuntimeFailStopped(f"runtime health is {self._health}")

    def _insert_message(
        self,
        envelope: RuntimeMessageEnvelope,
        registration: ComponentOccurrenceRegistration,
        envelope_hash: str,
    ) -> int:
        self._store_envelope(envelope, envelope_hash)
        position = self._insert_fact(
            "message_accepted",
            registration=registration,
            envelope=envelope,
            details={"envelope_hash": envelope_hash},
        )
        self._connection.execute(
            "INSERT INTO runtime_messages(message_id, envelope_hash, kind, "
            "trace_id, correlation_id, causation_id, status, accepted_position) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(envelope.message_id),
                envelope_hash,
                envelope.kind.value,
                str(envelope.trace_id),
                str(envelope.correlation_id) if envelope.correlation_id else None,
                str(envelope.causation_id) if envelope.causation_id else None,
                RuntimeDeliveryStatus.ACCEPTED.value,
                position,
            ),
        )
        return position

    def _store_envelope(
        self, envelope: RuntimeMessageEnvelope, envelope_hash: str
    ) -> None:
        encoded = cast(JsonObject, _encode(envelope))
        payload_value = cast(JsonObject, encoded.pop("payload"))
        payload_hash = self._store_json_payload(
            payload_value,
            content_type=envelope.payload.content_type,
            codec_id=envelope.payload.codec_id,
            codec_version=envelope.payload.codec_version,
        )
        self._connection.execute(
            "INSERT INTO runtime_envelopes"
            "(message_id, envelope_hash, payload_hash, envelope_metadata_json) "
            "VALUES (?, ?, ?, ?)",
            (
                str(envelope.message_id),
                envelope_hash,
                payload_hash,
                _canonical_json(encoded),
            ),
        )

    def _store_json_payload(
        self,
        value: JsonObject,
        *,
        content_type: str,
        codec_id: str,
        codec_version: int,
    ) -> str:
        payload_value = value
        payload_canonical = _canonical_json(payload_value).encode("utf-8")
        payload_hash = hashlib.sha256(payload_canonical).hexdigest()
        compression = "raw"
        payload_body = payload_canonical
        if len(payload_canonical) >= 1024:
            compressed = zlib.compress(payload_canonical, level=3)
            if len(compressed) < len(payload_canonical):
                compression = "zlib"
                payload_body = compressed
        self._connection.execute(
            "INSERT OR IGNORE INTO runtime_payloads"
            "(payload_hash, canonical_size, content_type, codec_id, codec_version, "
            "compression, payload_body) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload_hash,
                len(payload_canonical),
                content_type,
                codec_id,
                codec_version,
                compression,
                sqlite3.Binary(payload_body),
            ),
        )
        return payload_hash

    def _load_json_payload(self, payload_hash: str) -> JsonObject:
        row = self._connection.execute(
            "SELECT canonical_size, compression, payload_body FROM runtime_payloads "
            "WHERE payload_hash = ?",
            (payload_hash,),
        ).fetchone()
        if row is None:
            raise RuntimeLedgerUnavailable(f"payload is missing: {payload_hash}")
        body = bytes(row["payload_body"])
        canonical = zlib.decompress(body) if row["compression"] == "zlib" else body
        if len(canonical) != int(row["canonical_size"]):
            raise RuntimeLedgerUnavailable(f"payload size differs: {payload_hash}")
        if hashlib.sha256(canonical).hexdigest() != payload_hash:
            raise RuntimeLedgerUnavailable(f"payload digest differs: {payload_hash}")
        decoded = json.loads(canonical)
        if not isinstance(decoded, dict):
            raise RuntimeLedgerUnavailable(f"payload is not an object: {payload_hash}")
        return cast(JsonObject, decoded)

    def _effect_from_row(self, row: sqlite3.Row) -> JsonObject | None:
        details = cast(JsonObject, json.loads(str(row["details_json"])))
        payload_hash = details.get("effect_payload_hash")
        if not isinstance(payload_hash, str):
            return None
        return self._load_json_payload(payload_hash)

    def _load_envelope(self, message_id: UUID) -> RuntimeMessageEnvelope:
        row = self._connection.execute(
            "SELECT e.envelope_metadata_json, e.payload_hash, p.canonical_size, "
            "p.compression, p.payload_body FROM runtime_envelopes e "
            "JOIN runtime_payloads p ON p.payload_hash = e.payload_hash "
            "WHERE e.message_id = ?",
            (str(message_id),),
        ).fetchone()
        if row is None:
            raise RuntimeRegistrationInvalid(f"envelope is missing: {message_id}")
        body = bytes(row["payload_body"])
        canonical = zlib.decompress(body) if row["compression"] == "zlib" else body
        if len(canonical) != int(row["canonical_size"]):
            raise RuntimeLedgerUnavailable(f"payload size differs: {message_id}")
        if hashlib.sha256(canonical).hexdigest() != str(row["payload_hash"]):
            raise RuntimeLedgerUnavailable(f"payload digest differs: {message_id}")
        encoded = cast(JsonObject, json.loads(str(row["envelope_metadata_json"])))
        encoded["payload"] = json.loads(canonical)
        return _decode_envelope(encoded)

    def _fact(self, row: sqlite3.Row, *, include_payload: bool) -> RuntimeLedgerFact:
        message_id = UUID(str(row["message_id"])) if row["message_id"] else None
        return RuntimeLedgerFact(
            runtime_position=int(row["runtime_position"]),
            fact_type=str(row["fact_type"]),
            recorded_at=str(row["recorded_at"]),
            runtime_id=UUID(str(row["runtime_id"])),
            details=cast(JsonObject, json.loads(str(row["details_json"]))),
            instance_key=row["instance_key"],
            instance_id=UUID(str(row["instance_id"])) if row["instance_id"] else None,
            component_contract_id=row["component_contract_id"],
            message_id=message_id,
            trace_id=UUID(str(row["trace_id"])) if row["trace_id"] else None,
            correlation_id=(
                UUID(str(row["correlation_id"])) if row["correlation_id"] else None
            ),
            causation_id=UUID(str(row["causation_id"])) if row["causation_id"] else None,
            action_id=row["action_id"],
            schema_version=int(row["schema_version"]) if row["schema_version"] else None,
            envelope=(
                self._load_envelope(message_id)
                if include_payload and message_id is not None
                else None
            ),
        )

    def _finalize_trace(self, trace_id: UUID) -> tuple[int, RuntimeTraceDisposition] | None:
        terminal = self._connection.execute(
            "SELECT runtime_position, fact_type FROM runtime_ledger WHERE trace_id = ? "
            "AND fact_type IN ('trace_committed', 'trace_aborted', 'trace_indeterminate') "
            "ORDER BY runtime_position DESC LIMIT 1",
            (str(trace_id),),
        ).fetchone()
        if terminal is not None:
            return int(terminal["runtime_position"]), RuntimeTraceDisposition(
                str(terminal["fact_type"]).removeprefix("trace_")
            )
        rows = self._connection.execute(
            "SELECT * FROM runtime_messages WHERE trace_id = ? ORDER BY accepted_position",
            (str(trace_id),),
        ).fetchall()
        terminal_statuses = {
            RuntimeDeliveryStatus.COMPLETED.value,
            RuntimeDeliveryStatus.FAULTED.value,
            RuntimeDeliveryStatus.INDETERMINATE.value,
        }
        if not rows or any(row["status"] not in terminal_statuses for row in rows):
            return None
        roots = [row for row in rows if row["causation_id"] is None]
        if len(roots) != 1:
            raise sqlite3.DatabaseError("terminal trace must have one root")
        root = roots[0]
        disposition = RuntimeTraceDisposition(
            root["trace_disposition"] or RuntimeTraceDisposition.COMMITTED.value
        )
        if any(
            row["trace_disposition"] == RuntimeTraceDisposition.INDETERMINATE.value for row in rows
        ):
            disposition = RuntimeTraceDisposition.INDETERMINATE
        root_envelope = self._load_envelope(UUID(str(root["message_id"])))
        root_target = self._targets.get(root_envelope.target.instance_id)
        position = self._insert_fact(
            f"trace_{disposition.value}",
            registration=root_target.registration if root_target is not None else None,
            envelope=root_envelope,
            details={"root_message_id": str(root_envelope.message_id)},
        )
        self._connection.execute(
            "UPDATE runtime_messages SET terminal_position = ? WHERE message_id = ?",
            (position, str(root_envelope.message_id)),
        )
        recovery_trace = self._recovery_root == root_envelope.message_id
        if recovery_trace:
            self._recovery_root = None
        if self._health is not RuntimeHealth.FAIL_STOPPED:
            if disposition is RuntimeTraceDisposition.INDETERMINATE:
                self._transition_health(
                    RuntimeHealth.RECOVERY_REQUIRED,
                    f"trace indeterminate: {trace_id}",
                )
            elif recovery_trace and self._recovery_result_health is not None:
                result_health = self._recovery_result_health
                self._recovery_result_health = None
                self._transition_health(result_health, "recovery trace completed")
            elif self._health is RuntimeHealth.QUIESCING:
                self._transition_health(RuntimeHealth.READY, "quiesced trace completed")
        return position, disposition

    async def _query_history(self, query: RuntimeHistoryQuery) -> RuntimeHistoryPage:
        if not 1 <= query.limit <= 1000:
            raise ValueError("history limit must be between 1 and 1000")
        clauses, values = _history_clauses(query, self.runtime_id)
        values.append(query.limit + 1)
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT * FROM runtime_ledger WHERE "
                + " AND ".join(clauses)
                + " ORDER BY runtime_position LIMIT ?",
                tuple(values),
            ).fetchall()
        next_position = (
            int(rows[query.limit - 1]["runtime_position"]) if len(rows) > query.limit else None
        )
        return RuntimeHistoryPage(
            facts=tuple(
                self._fact(row, include_payload=query.include_payload)
                for row in rows[: query.limit]
            ),
            next_position=next_position,
        )

    async def _count_history(self, query: RuntimeHistoryQuery) -> int:
        clauses, values = _history_clauses(query, self.runtime_id)
        with self._db_lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS count FROM runtime_ledger WHERE " + " AND ".join(clauses),
                tuple(values),
            ).fetchone()
        return int(row["count"])

    async def _query_trace_summaries(
        self,
        *,
        after_position: int | None,
        limit: int,
        newest_first: bool,
        root_action_ids: tuple[str, ...],
    ) -> RuntimeTraceSummaryPage:
        if not 1 <= limit <= 500:
            raise ValueError("trace-summary limit must be between 1 and 500")
        clauses = [
            "runtime_id = ?",
            "fact_type IN ('trace_committed', 'trace_aborted', 'trace_indeterminate')",
        ]
        values: list[object] = [str(self.runtime_id)]
        if after_position is not None:
            clauses.append(
                "runtime_position < ?" if newest_first else "runtime_position > ?"
            )
            values.append(after_position)
        if root_action_ids:
            clauses.append("action_id IN (" + ",".join("?" for _ in root_action_ids) + ")")
            values.extend(root_action_ids)
        values.append(limit + 1)
        order = "DESC" if newest_first else "ASC"
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT runtime_position, fact_type, trace_id, message_id, action_id "
                "FROM runtime_ledger WHERE "
                + " AND ".join(clauses)
                + f" ORDER BY runtime_position {order} LIMIT ?",
                tuple(values),
            ).fetchall()
        visible = rows[:limit]
        summaries = tuple(
            RuntimeTraceSummary(
                trace_id=UUID(str(row["trace_id"])),
                root_message_id=UUID(str(row["message_id"])),
                root_action_id=str(row["action_id"]),
                terminal_position=int(row["runtime_position"]),
                disposition=RuntimeTraceDisposition(
                    str(row["fact_type"]).removeprefix("trace_")
                ),
            )
            for row in visible
        )
        return RuntimeTraceSummaryPage(
            summaries=summaries,
            next_position=(
                summaries[-1].terminal_position if len(rows) > limit and summaries else None
            ),
        )

    async def _get_trace(
        self, trace_id: UUID, *, include_payload: bool = False
    ) -> RuntimeCausalTrace:
        facts = await self._query_all_history(
            RuntimeHistoryQuery(
                trace_id=trace_id, limit=1000, include_payload=include_payload
            )
        )
        terminal = next(
            (
                RuntimeTraceDisposition(fact.fact_type.removeprefix("trace_"))
                for fact in reversed(facts)
                if fact.fact_type
                in {
                    "trace_committed",
                    "trace_aborted",
                    "trace_indeterminate",
                }
            ),
            None,
        )
        return RuntimeCausalTrace(trace_id, facts, terminal)

    async def _get_envelope(self, message_id: UUID) -> RuntimeMessageEnvelope | None:
        with self._db_lock:
            row = self._connection.execute(
                "SELECT 1 FROM runtime_messages WHERE message_id = ?", (str(message_id),)
            ).fetchone()
        return self._load_envelope(message_id) if row is not None else None

    async def _query_all_history(
        self, query: RuntimeHistoryQuery
    ) -> tuple[RuntimeLedgerFact, ...]:
        facts: list[RuntimeLedgerFact] = []
        after = query.after_position
        while True:
            page = await self._query_history(
                replace(query, after_position=after, limit=min(query.limit, 1000))
            )
            facts.extend(page.facts)
            if page.next_position is None:
                return tuple(facts)
            after = page.next_position

    async def _lookup_message_outcome(
        self, message_id: UUID
    ) -> RuntimeMessageOutcome | None:
        with self._db_lock:
            request_row = self._connection.execute(
                "SELECT * FROM runtime_messages WHERE message_id = ? AND kind = ?",
                (str(message_id), RuntimeMessageKind.REQUEST.value),
            ).fetchone()
            if request_row is None:
                return None
            terminal_row = self._connection.execute(
                "SELECT * FROM runtime_messages WHERE correlation_id = ? "
                "AND kind IN (?, ?) ORDER BY accepted_position LIMIT 1",
                (
                    str(message_id),
                    RuntimeMessageKind.RESPONSE.value,
                    RuntimeMessageKind.FAULT.value,
                ),
            ).fetchone()
            trace_terminal = self._connection.execute(
                "SELECT runtime_position, fact_type FROM runtime_ledger "
                "WHERE trace_id = ? AND fact_type IN "
                "('trace_committed','trace_aborted','trace_indeterminate') "
                "ORDER BY runtime_position DESC LIMIT 1",
                (str(request_row["trace_id"]),),
            ).fetchone()
        request = self._load_envelope(UUID(str(request_row["message_id"])))
        terminal = (
            self._load_envelope(UUID(str(terminal_row["message_id"])))
            if terminal_row is not None
            else None
        )
        terminal_receipt = (
            _receipt_from_row(
                cast(RuntimeMessageEnvelope, terminal),
                cast(sqlite3.Row, terminal_row),
            )
            if terminal_row is not None
            else None
        )
        if terminal_receipt is not None and trace_terminal is not None:
            terminal_receipt = replace(
                terminal_receipt,
                terminal_position=int(trace_terminal["runtime_position"]),
                trace_disposition=RuntimeTraceDisposition(
                    str(trace_terminal["fact_type"]).removeprefix("trace_")
                ),
            )
        return RuntimeMessageOutcome(
            request_envelope=request,
            request_receipt=_receipt_from_row(request, request_row),
            terminal_envelope=terminal,
            terminal_receipt=terminal_receipt,
        )

    async def _reconstruct(
        self, request: RuntimeReconstructionRequest
    ) -> RuntimeReconstructionReport:
        if self._health in {
            RuntimeHealth.FAIL_STOPPED,
            RuntimeHealth.CLOSING,
            RuntimeHealth.CLOSED,
            RuntimeHealth.BRANCH_PENDING,
        }:
            raise RuntimeFailStopped(f"runtime health is {self._health.value}")
        head = await self._current_position()
        through = head if request.through_position is None else request.through_position
        if through < 0 or through > head:
            raise RuntimeReplayIncompatible(
                "through_position must identify existing confirmed history"
            )
        with self._db_lock:
            open_rows = self._connection.execute(
                "SELECT message_id FROM runtime_messages WHERE status IN (?, ?)",
                (RuntimeDeliveryStatus.ACCEPTED.value, RuntimeDeliveryStatus.DELIVERING.value),
            ).fetchall()
        open_ids = {UUID(str(row["message_id"])) for row in open_rows}
        allowed_open = {self._recovery_root} if self._recovery_root is not None else set()
        if open_ids - allowed_open:
            raise RuntimeReplayTargetNotPrepared(
                "reconstruction requires terminal live deliveries"
            )

        state_owners = sorted(
            (
                target
                for target in self._targets.values()
                if target.registration.replay_authority is RuntimeReplayMode.CANONICAL_EFFECT
            ),
            key=lambda target: target.registration.instance_key,
        )
        owner_keys = {target.registration.instance_key for target in state_owners}
        external_targets = sorted(
            (
                target
                for target in self._targets.values()
                if target.registration.replay_authority is RuntimeReplayMode.EXTERNAL_EXCHANGE
            ),
            key=lambda target: target.registration.instance_key,
        )
        checkpoint_references = _checkpoint_references(request, owner_keys)
        if not request.reset_targets:
            for target in state_owners:
                status = await target.participant.replay_state_status()
                if not bool(getattr(status, "empty", False)):
                    raise RuntimeReplayTargetNotPrepared(
                        f"replay target is not empty: {target.registration.instance_key}"
                    )
        try:
            self._transition_health(RuntimeHealth.RECONSTRUCTING, "reconstruction started")
            for target in state_owners:
                if request.reset_targets:
                    await target.participant.reset_replay_state()

            start_position = 0
            checkpoint_cursors: set[int] = set()
            for target in state_owners:
                reference = checkpoint_references.get(target.registration.instance_key)
                if reference is not None:
                    checkpoint_cursors.add(
                        await target.participant.import_replay_checkpoint(reference)
                    )
            if len(checkpoint_cursors) > 1:
                raise RuntimeReplayIncompatible(
                    "all replay checkpoints must represent one runtime position"
                )
            if checkpoint_cursors:
                start_position = checkpoint_cursors.pop()
                if start_position < 0 or start_position > through:
                    raise RuntimeReplayIncompatible(
                        "checkpoint cursor must be within the reconstruction window"
                    )

            with self._db_lock:
                rows = self._connection.execute(
                    "SELECT e.*, t.fact_type AS terminal_fact, "
                    "t.runtime_position AS terminal_fact_position FROM runtime_ledger e "
                    "LEFT JOIN runtime_ledger t ON t.trace_id = e.trace_id "
                    "AND t.fact_type IN "
                    "('trace_committed','trace_aborted','trace_indeterminate') "
                    "WHERE e.fact_type = 'canonical_effect' "
                    "AND e.runtime_position > ? AND e.runtime_position <= ? "
                    "ORDER BY e.runtime_position",
                    (start_position, through),
                ).fetchall()
                external_effects_skipped = int(
                    self._connection.execute(
                        "SELECT COUNT(*) AS count FROM runtime_ledger "
                        "WHERE fact_type = 'external_exchange' "
                        "AND runtime_position > ? AND runtime_position <= ?",
                        (start_position, through),
                    ).fetchone()["count"]
                )
            committed = [
                row
                for row in rows
                if row["terminal_fact"] == "trace_committed"
                and int(row["terminal_fact_position"]) <= through
            ]
            selected = _select_effect_rows(committed, self._effect_from_row)
            applied = 0
            skipped = len(rows) - len(selected)
            incompatible = 0
            limitations: list[str] = []
            for _row, instance_key, effect in _expand_effects(
                selected,
                committed,
                self._effect_from_row,
                lambda message_id, ancestor_id: self._is_causal_descendant(
                    UUID(message_id), UUID(ancestor_id)
                ),
            ):
                registration = self._registrations_by_key.get(instance_key)
                target = self._targets.get(registration.instance_id) if registration else None
                if target is None:
                    incompatible += 1
                    limitations.append(f"effect target unavailable: {instance_key}")
                    continue
                try:
                    await target.participant.apply_replay_effect(effect)
                    applied += 1
                except Exception as error:
                    incompatible += 1
                    limitations.append(f"{instance_key}: {error}")

            state_digests: JsonObject = {}
            verified = incompatible == 0
            for target in state_owners:
                key = target.registration.instance_key
                digest = await target.participant.replay_state_digest()
                state_digests[key] = digest
                component_limitations = await target.participant.verify_replay_state()
                limitations.extend(f"{key}: {item}" for item in component_limitations)
                verified = verified and not component_limitations

            boundaries = _external_boundary_dispositions(request, external_targets)
            limitations.extend(
                f"{boundary.boundary_id}: {boundary.limitation}"
                for boundary in boundaries
                if boundary.limitation
            )
            verified_digest = _state_digest(state_digests) if verified else None
            source_runtime_id = request.source_runtime_id or self.runtime_id
            result_health = RuntimeHealth.RECOVERY_REQUIRED
            if verified and through < head:
                self._pending_branch = _PendingBranch(
                    source_runtime_id,
                    through,
                    cast(str, verified_digest),
                    state_digests,
                )
                self._persist_pending_branch(self._pending_branch)
                result_health = RuntimeHealth.BRANCH_PENDING
            elif verified:
                self._clear_pending_branch()
                result_health = RuntimeHealth.READY

            self._append_fact(
                "reconstruction_committed" if verified else "reconstruction_indeterminate",
                details={
                    "start_position": start_position,
                    "through_position": through,
                    "applied_effects": applied,
                    "incompatible_effects": incompatible,
                    "external_effects_skipped": external_effects_skipped,
                    "verified": verified,
                },
            )
            if self._recovery_root is None:
                self._transition_health(result_health, "reconstruction finished")
            else:
                self._recovery_result_health = result_health
            return RuntimeReconstructionReport(
                start_position=start_position,
                through_position=through,
                applied_effects=applied,
                skipped_effects=skipped,
                incompatible_effects=incompatible,
                state_digests=state_digests,
                verified=verified,
                external_effects_skipped=external_effects_skipped,
                external_boundaries=boundaries,
                limitations=tuple(limitations),
                verified_digest=verified_digest,
            )
        except Exception:
            self._recovery_result_health = None
            if self._health is not RuntimeHealth.FAIL_STOPPED:
                self._transition_health(
                    RuntimeHealth.RECOVERY_REQUIRED,
                    "reconstruction failed",
                )
            raise

    async def _record_branch_provenance(
        self, source_runtime_id: UUID, source_cursor: int, verified_digest: str
    ) -> int:
        pending = self._pending_branch
        if self._health is not RuntimeHealth.BRANCH_PENDING or pending is None:
            raise RuntimeReplayIncompatible("no verified historical branch is pending")
        if (
            source_runtime_id != pending.source_runtime_id
            or source_cursor != pending.source_cursor
            or verified_digest != pending.verified_digest
        ):
            raise RuntimeReplayIncompatible("branch provenance differs from reconstruction")
        current: JsonObject = {}
        for key in pending.state_digests:
            registration = self._registrations_by_key[key]
            current[key] = await self._targets[
                registration.instance_id
            ].participant.replay_state_digest()
        if _state_digest(current) != verified_digest:
            raise RuntimeReplayTargetNotPrepared("branch state changed before provenance")
        position = self._append_fact(
            "branch_provenance",
            details={
                "source_runtime_id": str(source_runtime_id),
                "source_cursor": source_cursor,
                "verified_digest": verified_digest,
            },
        )
        self._pending_branch = None
        self._clear_pending_branch()
        self._transition_health(RuntimeHealth.READY, "branch provenance recorded")
        return position

    async def _close(self) -> None:
        if self._health not in {RuntimeHealth.FAIL_STOPPED, RuntimeHealth.CLOSED}:
            self._transition_health(RuntimeHealth.CLOSING, "runtime close requested")
        for target in self._targets.values():
            for lane in target.lanes.values():
                for worker in lane.workers:
                    worker.cancel()
        await asyncio.gather(
            *(
                worker
                for target in self._targets.values()
                for lane in target.lanes.values()
                for worker in lane.workers
            ),
            return_exceptions=True,
        )
        if self._health is not RuntimeHealth.FAIL_STOPPED:
            self._append_fact("runtime_shutdown", details={"health": self._health.value})

    async def _enter_fail_stop(
        self, reason: str, envelope: RuntimeMessageEnvelope | None = None
    ) -> None:
        if self._health is not RuntimeHealth.FAIL_STOPPED:
            try:
                self._transition_health(RuntimeHealth.FAIL_STOPPED, reason)
            except Exception:
                self._health = RuntimeHealth.FAIL_STOPPED
        self._recovery_root = None
        self._recovery_result_health = None
        current = asyncio.current_task()
        active = [
            (task, active_envelope)
            for task, active_envelope in self._active_deliveries.values()
            if task is not current
            and (envelope is None or active_envelope.message_id != envelope.message_id)
        ]
        for task, _active_envelope in active:
            task.cancel()
        if active:
            await asyncio.gather(*(task for task, _ in active), return_exceptions=True)
        queued: list[RuntimeMessageEnvelope] = []
        for target in self._targets.values():
            for lane in target.lanes.values():
                while True:
                    try:
                        queued.append(lane.queue.get_nowait().envelope)
                        lane.queue.task_done()
                    except asyncio.QueueEmpty:
                        break
        affected = [active_envelope for _, active_envelope in active] + queued
        if envelope is not None:
            affected.append(envelope)
        seen: set[UUID] = set()
        for affected_envelope in affected:
            if affected_envelope.message_id in seen:
                continue
            seen.add(affected_envelope.message_id)
            try:
                await self._mark_indeterminate(
                    affected_envelope,
                    f"runtime fail-stop: {reason}",
                )
            except Exception:
                pass
        try:
            self._append_fact(
                "runtime_fail_stopped",
                envelope=envelope,
                details={"reason": reason},
            )
        except Exception:
            pass

    def _transition_health(self, health: RuntimeHealth, reason: str) -> None:
        if health is self._health:
            return
        allowed: dict[RuntimeHealth, set[RuntimeHealth]] = {
            RuntimeHealth.STARTING: {
                RuntimeHealth.READY,
                RuntimeHealth.RECOVERY_REQUIRED,
                RuntimeHealth.BRANCH_PENDING,
                RuntimeHealth.FAIL_STOPPED,
                RuntimeHealth.CLOSING,
            },
            RuntimeHealth.READY: {
                RuntimeHealth.QUIESCING,
                RuntimeHealth.RECONSTRUCTING,
                RuntimeHealth.RECOVERY_REQUIRED,
                RuntimeHealth.FAIL_STOPPED,
                RuntimeHealth.CLOSING,
            },
            RuntimeHealth.QUIESCING: {
                RuntimeHealth.READY,
                RuntimeHealth.RECOVERY_REQUIRED,
                RuntimeHealth.FAIL_STOPPED,
                RuntimeHealth.CLOSING,
            },
            RuntimeHealth.RECONSTRUCTING: {
                RuntimeHealth.READY,
                RuntimeHealth.RECOVERY_REQUIRED,
                RuntimeHealth.BRANCH_PENDING,
                RuntimeHealth.FAIL_STOPPED,
                RuntimeHealth.CLOSING,
            },
            RuntimeHealth.RECOVERY_REQUIRED: {
                RuntimeHealth.RECONSTRUCTING,
                RuntimeHealth.FAIL_STOPPED,
                RuntimeHealth.CLOSING,
            },
            RuntimeHealth.BRANCH_PENDING: {
                RuntimeHealth.READY,
                RuntimeHealth.RECONSTRUCTING,
                RuntimeHealth.FAIL_STOPPED,
                RuntimeHealth.CLOSING,
            },
            RuntimeHealth.FAIL_STOPPED: {RuntimeHealth.CLOSING},
            RuntimeHealth.CLOSING: {RuntimeHealth.CLOSED},
            RuntimeHealth.CLOSED: set(),
        }
        previous = self._health
        if health not in allowed[previous]:
            raise RuntimeFailStopped(
                f"invalid runtime health transition: {previous.value}->{health.value}"
            )
        self._health = health
        try:
            self._append_fact(
                "runtime_health_changed",
                details={
                    "from": previous.value,
                    "to": health.value,
                    "reason": reason,
                },
            )
        except Exception:
            if health is not RuntimeHealth.FAIL_STOPPED:
                self._health = RuntimeHealth.FAIL_STOPPED
            raise

    def _record_rejection(self, message: RuntimeMessageEnvelope, error: Exception) -> None:
        try:
            self._append_fact(
                "message_rejected",
                envelope=message,
                details={"failure_type": type(error).__name__, "message": str(error)},
            )
        except Exception:
            pass

    def _append_fact(
        self,
        fact_type: str,
        *,
        registration: ComponentOccurrenceRegistration | None = None,
        envelope: RuntimeMessageEnvelope | None = None,
        details: JsonObject | None = None,
    ) -> int:
        with self._db_lock, self._connection:
            return self._insert_fact(
                fact_type,
                registration=registration,
                envelope=envelope,
                details=details,
            )

    def _insert_fact(
        self,
        fact_type: str,
        *,
        registration: ComponentOccurrenceRegistration | None = None,
        envelope: RuntimeMessageEnvelope | None = None,
        details: JsonObject | None = None,
    ) -> int:
        if fact_type in self._fail_next_fact_types:
            self._fail_next_fact_types.remove(fact_type)
            raise RuntimeLedgerUnavailable(f"simulated ledger failure: {fact_type}")
        resolved_registration = registration
        if resolved_registration is None and envelope is not None:
            resolved_registration = next(
                (
                    item
                    for item in self._registrations_by_key.values()
                    if item.instance_id == envelope.target.instance_id
                ),
                None,
            )
        cursor = self._connection.execute(
            "INSERT INTO runtime_ledger(fact_type, recorded_at, runtime_id, instance_key, "
            "instance_id, component_contract_id, message_id, trace_id, correlation_id, "
            "causation_id, action_id, schema_version, message_kind, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fact_type,
                _now(),
                str(self.runtime_id),
                resolved_registration.instance_key if resolved_registration else None,
                str(resolved_registration.instance_id) if resolved_registration else None,
                (
                    envelope.component_contract_id
                    if envelope is not None
                    else resolved_registration.component_contract_id
                    if resolved_registration
                    else None
                ),
                str(envelope.message_id) if envelope else None,
                str(envelope.trace_id) if envelope else None,
                str(envelope.correlation_id) if envelope and envelope.correlation_id else None,
                str(envelope.causation_id) if envelope and envelope.causation_id else None,
                envelope.action_id if envelope else None,
                envelope.schema_version if envelope else None,
                envelope.kind.value if envelope else None,
                _canonical_json(details or {}),
            ),
        )
        if cursor.lastrowid is None:
            raise sqlite3.DatabaseError("ledger insert did not return a position")
        return int(cursor.lastrowid)

    def _initialize_schema(self, runtime_key: str, runtime_id: UUID | None) -> None:
        with self._db_lock:
            tables = {
                str(row["name"])
                for row in self._connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            if tables:
                if "runtime_metadata" not in tables:
                    raise RuntimeStorageVersionUnsupported(
                        "existing database is not a message-native runtime"
                    )
                row = self._connection.execute(
                    "SELECT value FROM runtime_metadata WHERE key = 'storage_schema_version'"
                ).fetchone()
                if row is None or int(row["value"]) != _STORAGE_SCHEMA_VERSION:
                    raise RuntimeStorageVersionUnsupported(
                        "runtime database belongs to the proxy-era generation; "
                        "restore a snapshot into a fresh data root"
                    )
                key_row = self._connection.execute(
                    "SELECT value FROM runtime_metadata WHERE key = 'runtime_key'"
                ).fetchone()
                if key_row is None or key_row["value"] != runtime_key:
                    raise RuntimeRegistrationInvalid("runtime key differs from durable metadata")
                return
            with self._connection:
                self._connection.executescript(
                    """
                    CREATE TABLE runtime_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE runtime_occurrences (
                        instance_key TEXT PRIMARY KEY,
                        instance_id TEXT NOT NULL UNIQUE,
                        component_contract_id TEXT NOT NULL,
                        binding_id TEXT NOT NULL,
                        binding_version INTEGER NOT NULL,
                        lanes_json TEXT NOT NULL,
                        replay_authority TEXT NOT NULL,
                        configuration_json TEXT NOT NULL
                    );
                    CREATE TABLE runtime_topology (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        manifest_hash TEXT NOT NULL,
                        manifest_json TEXT NOT NULL,
                        confirmed INTEGER NOT NULL,
                        topology_hash TEXT
                    );
                    CREATE TABLE runtime_payloads (
                        payload_hash TEXT PRIMARY KEY,
                        canonical_size INTEGER NOT NULL,
                        content_type TEXT NOT NULL,
                        codec_id TEXT NOT NULL,
                        codec_version INTEGER NOT NULL,
                        compression TEXT NOT NULL,
                        payload_body BLOB NOT NULL
                    );
                    CREATE TABLE runtime_envelopes (
                        message_id TEXT PRIMARY KEY,
                        envelope_hash TEXT NOT NULL,
                        payload_hash TEXT NOT NULL REFERENCES runtime_payloads(payload_hash),
                        envelope_metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE runtime_messages (
                        message_id TEXT PRIMARY KEY,
                        envelope_hash TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        trace_id TEXT NOT NULL,
                        correlation_id TEXT,
                        causation_id TEXT,
                        status TEXT NOT NULL,
                        accepted_position INTEGER NOT NULL,
                        terminal_position INTEGER,
                        trace_disposition TEXT
                    );
                    CREATE INDEX runtime_messages_trace
                        ON runtime_messages(trace_id, accepted_position);
                    CREATE TABLE runtime_ledger (
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
                        message_kind TEXT,
                        details_json TEXT NOT NULL
                    );
                    CREATE INDEX runtime_ledger_trace ON runtime_ledger(trace_id, runtime_position);
                    """
                )
                values = {
                    "storage_schema_version": str(_STORAGE_SCHEMA_VERSION),
                    "runtime_key": runtime_key,
                    "runtime_id": str(runtime_id or uuid4()),
                }
                self._connection.executemany(
                    "INSERT INTO runtime_metadata(key, value) VALUES (?, ?)", values.items()
                )

    def _metadata(self, key: str) -> str:
        with self._db_lock:
            row = self._connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            raise RuntimeStorageVersionUnsupported(f"runtime metadata is missing: {key}")
        return str(row["value"])

    def _load_registrations(self) -> None:
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT * FROM runtime_occurrences ORDER BY rowid"
            ).fetchall()
        for row in rows:
            registration = ComponentOccurrenceRegistration(
                instance_key=str(row["instance_key"]),
                instance_id=UUID(str(row["instance_id"])),
                component_contract_id=str(row["component_contract_id"]),
                binding_id=str(row["binding_id"]),
                binding_version=int(row["binding_version"]),
                lanes=tuple(
                    RuntimeLaneDeclaration(
                        name=str(item["name"]),
                        queue_capacity=int(item["queue_capacity"]),
                        worker_limit=int(item["worker_limit"]),
                    )
                    for item in json.loads(str(row["lanes_json"]))
                ),
                replay_authority=RuntimeReplayMode(str(row["replay_authority"])),
                configuration_references=tuple(json.loads(str(row["configuration_json"]))),
            )
            self._registrations_by_key[registration.instance_key] = registration
        self._manifest = self._load_manifest()

    def _load_manifest(self) -> RuntimeTopologyManifest | None:
        with self._db_lock:
            row = self._connection.execute(
                "SELECT manifest_json FROM runtime_topology WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row["manifest_json"]))
        return _decode_manifest(value)

    def _recover_incomplete_deliveries(self) -> bool:
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT * FROM runtime_messages WHERE status IN (?, ?)",
                (RuntimeDeliveryStatus.ACCEPTED.value, RuntimeDeliveryStatus.DELIVERING.value),
            ).fetchall()
        if not rows:
            return False
        with self._db_lock, self._connection:
            traces: set[UUID] = set()
            for row in rows:
                envelope = self._load_envelope(UUID(str(row["message_id"])))
                position = self._insert_fact(
                    "delivery_indeterminate",
                    envelope=envelope,
                    details={"reason": "runtime restarted with an open delivery"},
                )
                self._connection.execute(
                    "UPDATE runtime_messages SET status = ?, terminal_position = ?, "
                    "trace_disposition = ? WHERE message_id = ?",
                    (
                        RuntimeDeliveryStatus.INDETERMINATE.value,
                        position,
                        RuntimeTraceDisposition.INDETERMINATE.value,
                        str(envelope.message_id),
                    ),
                )
                traces.add(envelope.trace_id)
            for trace_id in traces:
                self._finalize_trace(trace_id)
        return True

    def _load_pending_branch(self) -> _PendingBranch | None:
        keys = {
            "branch_source_runtime_id",
            "branch_source_cursor",
            "branch_verified_digest",
            "branch_state_digests",
        }
        with self._db_lock:
            rows = self._connection.execute(
                "SELECT key, value FROM runtime_metadata WHERE key IN (?, ?, ?, ?)",
                tuple(keys),
            ).fetchall()
        values = {str(row["key"]): str(row["value"]) for row in rows}
        if set(values) != keys:
            return None
        return _PendingBranch(
            UUID(values["branch_source_runtime_id"]),
            int(values["branch_source_cursor"]),
            values["branch_verified_digest"],
            cast(JsonObject, json.loads(values["branch_state_digests"])),
        )

    def _persist_pending_branch(self, pending: _PendingBranch) -> None:
        values = {
            "branch_source_runtime_id": str(pending.source_runtime_id),
            "branch_source_cursor": str(pending.source_cursor),
            "branch_verified_digest": pending.verified_digest,
            "branch_state_digests": _canonical_json(pending.state_digests),
        }
        with self._db_lock, self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO runtime_metadata(key, value) VALUES (?, ?)",
                values.items(),
            )

    def _clear_pending_branch(self) -> None:
        with self._db_lock, self._connection:
            self._connection.execute("DELETE FROM runtime_metadata WHERE key LIKE 'branch_%'")


def _validate_declaration(declaration: ComponentOccurrenceDeclaration) -> None:
    if not declaration.instance_key.strip() or not declaration.component_contract_id.strip():
        raise RuntimeRegistrationInvalid("occurrence identities must be non-empty")
    if declaration.binding_version < 1 or not declaration.lanes:
        raise RuntimeRegistrationInvalid("binding version and lanes must be present")
    names = [lane.name for lane in declaration.lanes]
    if len(names) != len(set(names)) or _RESPONSE_LANE in names:
        raise RuntimeRegistrationInvalid("lane names must be unique and non-reserved")
    if any(
        not lane.name.strip() or lane.queue_capacity < 1 or lane.worker_limit < 1
        for lane in declaration.lanes
    ):
        raise RuntimeRegistrationInvalid("lane capacities and worker limits must be positive")


def _registration_matches(
    registration: ComponentOccurrenceRegistration,
    declaration: ComponentOccurrenceDeclaration,
) -> bool:
    return (
        registration.instance_key == declaration.instance_key
        and registration.component_contract_id == declaration.component_contract_id
        and registration.binding_id == declaration.binding_id
        and registration.binding_version == declaration.binding_version
        and registration.lanes == declaration.lanes
        and registration.replay_authority == declaration.replay_authority
        and registration.configuration_references == declaration.configuration_references
    )


def _receipt_from_row(message: RuntimeMessageEnvelope, row: sqlite3.Row) -> RuntimeMessageReceipt:
    return RuntimeMessageReceipt(
        message_id=message.message_id,
        trace_id=message.trace_id,
        accepted_position=int(row["accepted_position"]),
        status=RuntimeDeliveryStatus(str(row["status"])),
        terminal_position=(
            int(row["terminal_position"]) if row["terminal_position"] is not None else None
        ),
        trace_disposition=(
            RuntimeTraceDisposition(str(row["trace_disposition"]))
            if row["trace_disposition"] is not None
            else None
        ),
    )


def _history_clauses(
    query: RuntimeHistoryQuery, runtime_id: UUID
) -> tuple[list[str], list[object]]:
    clauses = ["runtime_id = ?", "runtime_position > ?"]
    values: list[object] = [str(query.runtime_id or runtime_id), query.after_position or 0]
    filters: tuple[tuple[str, object | None], ...] = (
        ("runtime_position <= ?", query.through_position),
        ("recorded_at > ?", query.after_time),
        ("recorded_at <= ?", query.through_time),
        ("instance_key = ?", query.instance_key),
        ("instance_id = ?", str(query.instance_id) if query.instance_id else None),
        ("component_contract_id = ?", query.component_contract_id),
        ("message_id = ?", str(query.message_id) if query.message_id else None),
        ("trace_id = ?", str(query.trace_id) if query.trace_id else None),
        ("correlation_id = ?", str(query.correlation_id) if query.correlation_id else None),
        ("causation_id = ?", str(query.causation_id) if query.causation_id else None),
        ("action_id = ?", query.action_id),
        ("schema_version = ?", query.schema_version),
        ("fact_type = ?", query.fact_type),
        ("message_kind = ?", query.message_kind.value if query.message_kind else None),
    )
    for clause, value in filters:
        if value is not None:
            clauses.append(clause)
            values.append(value)
    if query.delivery_status is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM runtime_messages m WHERE m.message_id = "
            "runtime_ledger.message_id AND m.status = ?)"
        )
        values.append(query.delivery_status.value)
    if query.trace_disposition is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM runtime_ledger t WHERE t.trace_id = "
            "runtime_ledger.trace_id AND t.fact_type = ?)"
        )
        values.append(f"trace_{query.trace_disposition.value}")
    return clauses, values


def _select_effect_rows(
    rows: list[sqlite3.Row],
    load_effect: Callable[[sqlite3.Row], JsonObject | None],
) -> list[sqlite3.Row]:
    by_trace: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_trace.setdefault(str(row["trace_id"]), []).append(row)
    selected: list[sqlite3.Row] = []
    for trace_rows in by_trace.values():
        superseding: list[sqlite3.Row] = []
        for row in trace_rows:
            effect = load_effect(row)
            payload = effect.get("payload") if effect is not None else None
            if isinstance(payload, dict) and payload.get("supersedes_trace_effects") is True:
                superseding.append(row)
        selected.extend([superseding[-1]] if superseding else trace_rows)
    return sorted(selected, key=lambda row: int(row["runtime_position"]))


def _checkpoint_references(
    request: RuntimeReconstructionRequest,
    owner_keys: set[str],
) -> dict[str, str]:
    if request.checkpoint_reference is not None and request.checkpoint_references:
        raise RuntimeReplayIncompatible(
            "use checkpoint_reference or checkpoint_references, not both"
        )
    if request.checkpoint_reference is not None:
        if len(owner_keys) != 1:
            raise RuntimeReplayIncompatible(
                "checkpoint_reference requires exactly one canonical state owner"
            )
        return {next(iter(owner_keys)): request.checkpoint_reference}
    if not request.checkpoint_references:
        return {}
    if set(request.checkpoint_references) != owner_keys:
        raise RuntimeReplayIncompatible(
            "checkpoint_references must identify every canonical state owner"
        )
    if any(
        not isinstance(reference, str) or not reference.strip()
        for reference in request.checkpoint_references.values()
    ):
        raise RuntimeReplayIncompatible("checkpoint references must be non-empty strings")
    return {
        key: cast(str, reference)
        for key, reference in request.checkpoint_references.items()
    }


def _external_boundary_dispositions(
    request: RuntimeReconstructionRequest,
    targets: list[_TargetState],
) -> tuple[RuntimeExternalBoundaryDisposition, ...]:
    known = {target.registration.instance_key for target in targets}
    provided: dict[str, RuntimeExternalBoundaryDisposition] = {}
    for disposition in request.external_boundaries:
        if disposition.boundary_id in provided:
            raise RuntimeReplayIncompatible(
                f"duplicate external boundary: {disposition.boundary_id}"
            )
        if disposition.boundary_id not in known:
            raise RuntimeReplayIncompatible(
                f"unknown external boundary: {disposition.boundary_id}"
            )
        provided[disposition.boundary_id] = disposition
    return tuple(
        provided.get(
            key,
            RuntimeExternalBoundaryDisposition(
                boundary_id=key,
                mode=RuntimeExternalBoundaryMode.PLAYBACK_ONLY,
            ),
        )
        for key in sorted(known)
    )


def _expand_effects(
    rows: list[sqlite3.Row],
    available_rows: list[sqlite3.Row],
    load_effect: Callable[[sqlite3.Row], JsonObject | None],
    is_causal_descendant: Callable[[str, str], bool],
) -> list[tuple[sqlite3.Row, str, JsonObject]]:
    available = {
        str(row["message_id"]): row
        for row in available_rows
        if row["message_id"] is not None
    }
    expanded: list[tuple[sqlite3.Row, str, JsonObject]] = []
    for row in rows:
        effect = load_effect(row)
        if not isinstance(effect, dict):
            continue
        payload = effect.get("payload")
        references = (
            payload.get("canonical_effect_references") if isinstance(payload, dict) else None
        )
        if isinstance(references, list):
            seen: set[str] = set()
            previous_position = -1
            for item in references:
                if not isinstance(item, dict):
                    raise RuntimeReplayIncompatible("aggregate effect reference is malformed")
                message_id = item.get("request_message_id")
                digest = item.get("effect_digest")
                if not isinstance(message_id, str) or not isinstance(digest, str):
                    raise RuntimeReplayIncompatible("aggregate effect reference is incomplete")
                if message_id in seen:
                    raise RuntimeReplayIncompatible("aggregate effect reference is duplicated")
                seen.add(message_id)
                child = available.get(message_id)
                if child is None:
                    raise RuntimeReplayIncompatible("aggregate effect reference is missing")
                if child["trace_id"] != row["trace_id"]:
                    raise RuntimeReplayIncompatible("aggregate effect crosses traces")
                if not is_causal_descendant(message_id, str(row["message_id"])):
                    raise RuntimeReplayIncompatible(
                        "aggregate effect reference is not a causal descendant"
                    )
                child_position = int(child["runtime_position"])
                if child_position <= previous_position or child_position >= int(
                    row["runtime_position"]
                ):
                    raise RuntimeReplayIncompatible("aggregate effect references are out of order")
                previous_position = child_position
                details = json.loads(str(child["details_json"]))
                if details.get("effect_digest") != digest:
                    raise RuntimeReplayIncompatible("aggregate effect digest differs")
                child_effect = load_effect(child)
                if child_effect is None or child["instance_key"] is None:
                    raise RuntimeReplayIncompatible("aggregate reference has no replayable effect")
                expanded.append((row, str(child["instance_key"]), child_effect))
        elif isinstance(payload, dict) and "aggregate_effects" in payload:
            raise RuntimeReplayIncompatible("embedded aggregate effects are unsupported")
        elif row["instance_key"] is not None:
            expanded.append((row, str(row["instance_key"]), cast(JsonObject, effect)))
    return expanded


def _state_digest(digests: JsonObject) -> str:
    return hashlib.sha256(_canonical_json(digests).encode()).hexdigest()


def _topology_hash(manifest: RuntimeTopologyManifest) -> str:
    value = {
        "runtime_key": manifest.runtime_key,
        "manifest_schema_version": manifest.manifest_schema_version,
        "occurrences": _encode(manifest.occurrences),
        "curated_operations": _encode(manifest.curated_operations),
        "curated_registration_digest": manifest.curated_registration_digest,
    }
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _decode_envelope(value: dict[str, object]) -> RuntimeMessageEnvelope:
    payload = cast(dict[str, object], value["payload"])
    source = cast(dict[str, object], value["source"])
    target = cast(dict[str, object], value["target"])
    return RuntimeMessageEnvelope(
        message_id=UUID(str(value["message_id"])),
        kind=RuntimeMessageKind(str(value["kind"])),
        source=RuntimeAddress(UUID(str(source["runtime_id"])), UUID(str(source["instance_id"]))),
        target=RuntimeAddress(UUID(str(target["runtime_id"])), UUID(str(target["instance_id"]))),
        component_contract_id=str(value["component_contract_id"]),
        action_id=str(value["action_id"]),
        schema_version=int(cast(int | str, value["schema_version"])),
        trace_id=UUID(str(value["trace_id"])),
        correlation_id=UUID(str(value["correlation_id"])) if value.get("correlation_id") else None,
        causation_id=UUID(str(value["causation_id"])) if value.get("causation_id") else None,
        idempotency_key=str(value["idempotency_key"]) if value.get("idempotency_key") else None,
        created_at=str(value["created_at"]),
        payload=RuntimePayload(
            codec_id=str(payload["codec_id"]),
            codec_version=int(cast(int | str, payload["codec_version"])),
            content_type=str(payload["content_type"]),
            value=cast(JsonValue, payload["value"]),
        ),
    )


def _decode_manifest(value: dict[str, object]) -> RuntimeTopologyManifest:
    occurrences = []
    for raw in cast(list[dict[str, object]], value["occurrences"]):
        occurrences.append(
            ComponentOccurrenceDeclaration(
                instance_key=str(raw["instance_key"]),
                component_contract_id=str(raw["component_contract_id"]),
                binding_id=str(raw["binding_id"]),
                binding_version=int(cast(int | str, raw["binding_version"])),
                lanes=tuple(
                    RuntimeLaneDeclaration(
                        str(lane["name"]),
                        int(cast(int | str, lane["queue_capacity"])),
                        int(cast(int | str, lane["worker_limit"])),
                    )
                    for lane in cast(list[dict[str, object]], raw["lanes"])
                ),
                replay_authority=RuntimeReplayMode(str(raw["replay_authority"])),
                configuration_references=tuple(
                    str(item) for item in cast(list[object], raw["configuration_references"])
                ),
            )
        )
    from components.runtime.messaging import RuntimeCuratedOperationDeclaration

    curated = tuple(
        RuntimeCuratedOperationDeclaration(
            operation_id=str(raw["operation_id"]),
            target_instance_key=str(raw["target_instance_key"]),
            component_contract_id=str(raw["component_contract_id"]),
            action_id=str(raw["action_id"]),
            schema_version=int(cast(int | str, raw["schema_version"])),
            binding_id=str(raw["binding_id"]),
            binding_version=int(cast(int | str, raw["binding_version"])),
            request_codec_id=str(raw["request_codec_id"]),
            request_codec_version=int(cast(int | str, raw["request_codec_version"])),
            request_payload_disposition=RuntimePayloadDisposition(
                str(raw["request_payload_disposition"])
            ),
            result_payload_disposition=RuntimePayloadDisposition(
                str(raw["result_payload_disposition"])
            ),
            fault_payload_disposition=RuntimePayloadDisposition(
                str(raw["fault_payload_disposition"])
            ),
            effect_payload_disposition=(
                RuntimePayloadDisposition(str(raw["effect_payload_disposition"]))
                if raw.get("effect_payload_disposition") is not None
                else None
            ),
        )
        for raw in cast(list[dict[str, object]], value["curated_operations"])
    )
    return RuntimeTopologyManifest(
        runtime_key=str(value["runtime_key"]),
        manifest_schema_version=int(cast(int | str, value["manifest_schema_version"])),
        occurrences=tuple(occurrences),
        curated_operations=curated,
        manifest_hash=str(value["manifest_hash"]),
        curated_registration_digest=(
            str(value["curated_registration_digest"])
            if value.get("curated_registration_digest") is not None
            else None
        ),
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
    raise TypeError(f"not canonically encodable: {type(value).__name__}")


def _require_json(value: object, path: str = "payload") -> None:
    if value is None or isinstance(value, str | int | float | bool):
        if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key, item in value.items():
            _require_json(item, f"{path}.{key}")
        return
    raise TypeError(f"{path} is not canonical JSON")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _now() -> str:
    return datetime.now(UTC).isoformat()
