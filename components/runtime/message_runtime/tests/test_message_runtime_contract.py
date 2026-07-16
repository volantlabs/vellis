from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import cast
from uuid import UUID, uuid4

import pytest

from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ComponentEndpoint,
    ComponentExecution,
    ReplayStateBinding,
    RuntimeComponentDeadlineExceeded,
)
from components.runtime.message_runtime import (
    RuntimeDeliveryUnknown,
    RuntimeFailStopped,
    RuntimeHistoryQuery,
    RuntimeLedgerUnavailable,
    RuntimeMessageConflict,
    RuntimeRegistrationInvalid,
    RuntimeReplayIncompatible,
    RuntimeReplayTargetNotPrepared,
    RuntimeRequestTimedOut,
    RuntimeTraceDisposition,
    SqliteMessageRuntime,
)
from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    JsonObject,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeCanonicalEffectReference,
    RuntimeCuratedOperationDeclaration,
    RuntimeExternalBoundaryDisposition,
    RuntimeExternalBoundaryMode,
    RuntimeHealth,
    RuntimeLaneDeclaration,
    RuntimePayloadDisposition,
    RuntimeReconstructionRequest,
    RuntimeReplayMode,
    RuntimeStorageVersionUnsupported,
    RuntimeTopologyManifest,
    topology_manifest_hash,
)

_CONTRACT = "component.test.counter"
_BINDING = "binding.test.counter.v2"


def test_old_or_unrecognized_runtime_storage_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "old.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE legacy_ledger(position INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeStorageVersionUnsupported):
        SqliteMessageRuntime(database, runtime_key="test.runtime")


MODEL_EVIDENCE = {
    "MessageRuntimeBoundaryVerification": (
        "test_uniform_delivery_is_durable_deduplicated_and_traceable",
        "test_initial_append_failure_prevents_dispatch_and_terminal_failure_fail_stops",
        "test_fail_stop_cancels_active_delivery_and_drains_queued_work",
        "test_deadline_compensation_holds_quiescing_then_aborts_safely",
        "test_failed_deadline_compensation_requires_recovery",
        "test_lane_fifo_cross_lane_overlap_and_writer_preference",
        "test_restart_marks_open_delivery_indeterminate",
    ),
    "RuntimeParticipantClosureVerification": (
        "test_uniform_delivery_is_durable_deduplicated_and_traceable",
    ),
    "RuntimeTopologyVerification": ("test_topology_is_atomic_and_identity_is_durable",),
    "RuntimeReconstructionVerification": (
        "test_reconstruction_requires_effect_and_commit_within_cursor",
        "test_checkpoint_reconstruction_requires_one_common_cursor",
        "test_reconstruction_failure_after_partial_reset_requires_recovery",
        "test_external_boundaries_are_reported_without_replay_invocation",
        "test_replay_state_spi_is_available_to_runtime",
        "test_superseding_aggregate_replays_referenced_child_effects_and_validates_digest",
    ),
    "AttachRuntimeParticipantContractVerification": (
        "test_topology_is_atomic_and_identity_is_durable",
    ),
    "CompleteRuntimeDeliveryContractVerification": (
        "test_uniform_delivery_is_durable_deduplicated_and_traceable",
    ),
    "FaultRuntimeDeliveryContractVerification": ("test_faults_use_the_same_durable_response_lane",),
    "AcknowledgeRuntimeDeliveryContractVerification": ("test_signals_close_by_acknowledgement",),
    "GetRuntimeHealthContractVerification": (
        "test_initial_append_failure_prevents_dispatch_and_terminal_failure_fail_stops",
    ),
    "AddressForRuntimeOccurrenceContractVerification": (
        "test_topology_is_atomic_and_identity_is_durable",
    ),
    "GetCurrentRuntimePositionContractVerification": (
        "test_history_is_cursor_paginated_and_filterable",
    ),
    "AcloseMessageRuntimeContractVerification": (
        "test_topology_is_atomic_and_identity_is_durable",
    ),
    "RegisterComponentOccurrenceContractVerification": (
        "test_topology_is_atomic_and_identity_is_durable",
    ),
    "PrepareStaticRuntimeTopologyContractVerification": (
        "test_topology_is_atomic_and_identity_is_durable",
    ),
    "ConfirmStaticRuntimeTopologyContractVerification": (
        "test_topology_is_atomic_and_identity_is_durable",
    ),
    "SendRuntimeMessageContractVerification": (
        "test_initial_append_failure_prevents_dispatch_and_terminal_failure_fail_stops",
    ),
    "QueryRuntimeHistoryContractVerification": ("test_history_is_cursor_paginated_and_filterable",),
    "CountRuntimeHistoryContractVerification": ("test_history_is_cursor_paginated_and_filterable",),
    "QueryRuntimeTraceSummariesContractVerification": (
        "test_history_is_cursor_paginated_and_filterable",
    ),
    "GetRuntimeCausalTraceContractVerification": (
        "test_uniform_delivery_is_durable_deduplicated_and_traceable",
        "test_get_trace_has_no_one_thousand_fact_cap",
    ),
    "GetRuntimeMessageEnvelopeContractVerification": (
        "test_payload_storage_is_lossless_compressed_and_history_is_metadata_first",
    ),
    "LookupRuntimeMessageOutcomeContractVerification": (
        "test_caller_timeout_does_not_cancel_execution_and_outcome_is_queryable",
    ),
    "ReconstructRuntimeStateContractVerification": (
        "test_reconstruction_requires_effect_and_commit_within_cursor",
        "test_checkpoint_reconstruction_requires_one_common_cursor",
        "test_reconstruction_failure_after_partial_reset_requires_recovery",
        "test_external_boundaries_are_reported_without_replay_invocation",
        "test_superseding_aggregate_replays_referenced_child_effects_and_validates_digest",
    ),
    "RecordRuntimeBranchProvenanceContractVerification": (
        "test_branch_provenance_requires_matching_reconstruction",
    ),
    "ReplayStateStatusContractVerification": ("test_replay_state_spi_is_available_to_runtime",),
    "ResetReplayStateContractVerification": ("test_replay_state_spi_is_available_to_runtime",),
    "ImportReplayCheckpointContractVerification": (
        "test_replay_state_spi_is_available_to_runtime",
    ),
    "ReplayStateDigestContractVerification": ("test_replay_state_spi_is_available_to_runtime",),
    "VerifyReplayStateContractVerification": ("test_replay_state_spi_is_available_to_runtime",),
}


class _Counter:
    def __init__(self) -> None:
        self.value = 0
        self.calls = 0

    def add(self, amount: int) -> int:
        self.calls += 1
        self.value += amount
        return self.value


def _descriptor(
    name: str,
    *,
    lane: str = "serialized",
    replay: RuntimeReplayMode = RuntimeReplayMode.NO_STATE_EFFECT,
    group: str | None = None,
    access="independent",
    deadline_seconds: float | None = None,
) -> RuntimeActionBindingDescriptor:
    from components.runtime.messaging import RuntimeConsistencyAccess

    return RuntimeActionBindingDescriptor(
        _CONTRACT,
        f"{_CONTRACT}.{name}",
        _BINDING,
        1,
        1,
        f"codec.test.{name}.request.json",
        f"codec.test.{name}.result.json",
        f"codec.test.{name}.failure.json",
        RuntimeActionIdempotency.UNSPECIFIED,
        replay,
        concurrency_lane=lane,
        consistency_group=group,
        consistency_access=RuntimeConsistencyAccess(access),
        deadline_seconds=deadline_seconds,
    )


def _counter_adapter(counter: _Counter) -> ComponentAdapter:
    return ComponentAdapter(
        (
            ActionBinding(
                _descriptor("add"),
                lambda payload: ((int(payload["amount"]),), {}),
                lambda value: int(cast(int, value)),
                invoke=counter.add,
            ),
        )
    )


def _replayable_counter_adapter(counter: _Counter) -> ComponentAdapter:
    descriptor = _descriptor("add", replay=RuntimeReplayMode.CANONICAL_EFFECT)
    return ComponentAdapter(
        (
            ActionBinding(
                descriptor,
                lambda payload: ((int(payload["amount"]),), {}),
                lambda value: int(cast(int, value)),
                invoke=counter.add,
                build_replay_effect=lambda args, _kwargs, _result: {
                    "amount": int(cast(int, args[0]))
                },
                apply_replay_effect=lambda effect: counter.add(int(effect["amount"])),
            ),
        ),
        replay_state=ReplayStateBinding(
            is_empty=lambda: counter.value == 0,
            reset=lambda: setattr(counter, "value", 0),
            import_checkpoint=lambda reference: int(reference.rsplit(":", 1)[-1]),
            export_state=lambda: {"value": counter.value},
        ),
    )


async def _compose(
    path: Path,
    participant: ComponentAdapter,
    *,
    lanes: tuple[RuntimeLaneDeclaration, ...] = (RuntimeLaneDeclaration("serialized"),),
    replay_authority: RuntimeReplayMode = RuntimeReplayMode.NO_STATE_EFFECT,
) -> tuple[SqliteMessageRuntime, ComponentEndpoint, RuntimeTopologyManifest]:
    runtime = SqliteMessageRuntime(path, runtime_key="test.runtime")
    ingress = ComponentAdapter(
        binding_id="binding.test.ingress", component_contract_id="component.test.ingress"
    )
    declarations = (
        ComponentOccurrenceDeclaration(
            "target",
            _CONTRACT,
            _BINDING,
            1,
            lanes=lanes,
            replay_authority=replay_authority,
        ),
        ComponentOccurrenceDeclaration(
            "ingress", "component.test.ingress", "binding.test.ingress", 1
        ),
    )
    manifest = RuntimeTopologyManifest("test.runtime", 4, declarations, (), "")
    manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
    await runtime.prepare_static_topology(manifest)
    target = await runtime.register_occurrence(declarations[0])
    source = await runtime.register_occurrence(declarations[1])
    await runtime.attach_participant(target, participant, participant.describe().actions)
    await runtime.attach_participant(source, ingress)
    await runtime.confirm_static_topology(manifest)
    return (
        runtime,
        ComponentEndpoint(runtime, ingress, source=runtime.address_for("ingress")),
        manifest,
    )


def test_uniform_delivery_is_durable_deduplicated_and_traceable(tmp_path: Path) -> None:
    async def exercise() -> None:
        counter = _Counter()
        runtime, endpoint, _ = await _compose(
            tmp_path / "runtime.sqlite", _counter_adapter(counter)
        )
        message_id = uuid4()
        first = await endpoint.request(
            _descriptor("add").action_ref(),
            {"amount": 3},
            target=runtime.address_for("target"),
            message_id=message_id,
        )
        duplicate = await endpoint.request(
            _descriptor("add").action_ref(),
            {"amount": 3},
            target=runtime.address_for("target"),
            message_id=message_id,
        )
        assert counter.value == 3 and counter.calls == 1
        assert duplicate.response == first.response
        assert duplicate.terminal_position == first.terminal_position
        with pytest.raises(RuntimeMessageConflict):
            await endpoint.request(
                _descriptor("add").action_ref(),
                {"amount": 4},
                target=runtime.address_for("target"),
                message_id=message_id,
            )
        trace = await runtime.get_trace(first.request.trace_id, include_payload=True)
        kinds = [
            fact.envelope.kind.value
            for fact in trace.facts
            if fact.fact_type == "message_accepted" and fact.envelope is not None
        ]
        assert kinds == ["request", "response"]
        assert trace.disposition is RuntimeTraceDisposition.COMMITTED
        await runtime.aclose()

    asyncio.run(exercise())


def test_payload_storage_is_lossless_compressed_and_history_is_metadata_first(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"

    async def exercise() -> None:
        runtime, endpoint, _ = await _compose(database, _counter_adapter(_Counter()))
        payload = {"amount": 1, "padding": "same-value-" * 300}
        # The counter codec ignores the extra modeled-test fixture field while storage retains it.
        outcome = await endpoint.request(
            _descriptor("add").action_ref(), payload, target=runtime.address_for("target")
        )
        await endpoint.request(
            _descriptor("add").action_ref(), payload, target=runtime.address_for("target")
        )
        envelope = await runtime.get_envelope(outcome.request.message_id)
        assert envelope is not None
        assert envelope.payload.value == payload
        page = await runtime.query_history(
            RuntimeHistoryQuery(trace_id=outcome.request.trace_id, limit=1000)
        )
        assert all(fact.envelope is None for fact in page.facts)
        hydrated = await runtime.query_history(
            RuntimeHistoryQuery(trace_id=outcome.request.trace_id, limit=1000, include_payload=True)
        )
        assert any(
            fact.envelope is not None
            and fact.envelope.payload.value.get("padding") == payload["padding"]
            for fact in hydrated.facts
            if isinstance(fact.envelope.payload.value if fact.envelope else None, dict)
        )
        await runtime.aclose()

    asyncio.run(exercise())
    connection = sqlite3.connect(database)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(runtime_ledger)").fetchall()}
    assert "envelope_json" not in columns
    payload_rows = connection.execute(
        "SELECT canonical_size, length(payload_body), compression FROM runtime_payloads "
        "WHERE canonical_size >= 1024"
    ).fetchall()
    assert payload_rows
    assert all(mode == "zlib" and stored < canonical for canonical, stored, mode in payload_rows)
    assert database.stat().st_mode & 0o777 == 0o600


def test_faults_use_the_same_durable_response_lane(tmp_path: Path) -> None:
    async def exercise() -> None:
        def fail(_amount: int) -> int:
            raise ValueError("blocked")

        adapter = ComponentAdapter(
            (
                ActionBinding(
                    _descriptor("add"),
                    lambda payload: ((int(payload["amount"]),), {}),
                    lambda value: int(cast(int, value)),
                    invoke=fail,
                    failure_types=(ValueError,),
                ),
            )
        )
        runtime, endpoint, _ = await _compose(tmp_path / "fault.sqlite", adapter)
        outcome = await endpoint.request(
            _descriptor("add").action_ref(), {"amount": 1}, target=runtime.address_for("target")
        )
        assert outcome.response.kind.value == "fault"
        assert outcome.trace_disposition is RuntimeTraceDisposition.ABORTED
        await runtime.aclose()

    asyncio.run(exercise())


def test_initial_append_failure_prevents_dispatch_and_terminal_failure_fail_stops(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        counter = _Counter()
        runtime, endpoint, _ = await _compose(tmp_path / "fail.sqlite", _counter_adapter(counter))
        runtime.simulate_ledger_failure_once("message_accepted")
        with pytest.raises(RuntimeLedgerUnavailable):
            await endpoint.request(
                _descriptor("add").action_ref(), {"amount": 1}, target=runtime.address_for("target")
            )
        assert counter.calls == 0
        runtime.simulate_ledger_failure_once("delivery_completed")
        with pytest.raises(RuntimeRequestTimedOut):
            await endpoint.request(
                _descriptor("add").action_ref(),
                {"amount": 2},
                target=runtime.address_for("target"),
                timeout_seconds=0.05,
            )
        assert counter.value == 2
        assert runtime.health is RuntimeHealth.FAIL_STOPPED
        await runtime.aclose()

    asyncio.run(exercise())


def test_fail_stop_cancels_active_delivery_and_drains_queued_work(tmp_path: Path) -> None:
    async def exercise() -> None:
        started = Event()
        release = Event()
        counter = _Counter()

        def delayed_add(amount: int) -> int:
            started.set()
            release.wait()
            return counter.add(amount)

        descriptor = _descriptor("add")
        adapter = ComponentAdapter(
            (
                ActionBinding(
                    descriptor,
                    lambda payload: ((int(payload["amount"]),), {}),
                    lambda value: int(cast(int, value)),
                    invoke=delayed_add,
                ),
            )
        )
        runtime, endpoint, _ = await _compose(tmp_path / "fail-stop.sqlite", adapter)
        first_id, second_id = uuid4(), uuid4()
        first = asyncio.create_task(
            endpoint.request(
                descriptor.action_ref(),
                {"amount": 1},
                target=runtime.address_for("target"),
                timeout_seconds=0.2,
                message_id=first_id,
            )
        )
        assert await asyncio.to_thread(started.wait, 1)
        second = asyncio.create_task(
            endpoint.request(
                descriptor.action_ref(),
                {"amount": 10},
                target=runtime.address_for("target"),
                timeout_seconds=0.2,
                message_id=second_id,
            )
        )
        queued = None
        for _ in range(100):
            queued = await runtime.lookup_message_outcome(second_id)
            if queued is not None:
                break
            await asyncio.sleep(0.005)
        assert queued is not None
        assert queued.request_receipt.status.value == "accepted"

        runtime.simulate_ledger_failure_once("delivery_completed")
        release.set()
        await asyncio.gather(first, second, return_exceptions=True)

        assert counter.calls == 1
        assert runtime.health is RuntimeHealth.FAIL_STOPPED
        first_outcome = await runtime.lookup_message_outcome(first_id)
        second_outcome = await runtime.lookup_message_outcome(second_id)
        assert first_outcome is not None
        assert second_outcome is not None
        assert first_outcome.request_receipt.status.value == "indeterminate"
        assert second_outcome.request_receipt.status.value == "indeterminate"
        with pytest.raises(RuntimeFailStopped):
            await endpoint.request(
                descriptor.action_ref(),
                {"amount": 100},
                target=runtime.address_for("target"),
            )
        await runtime.aclose()

    asyncio.run(exercise())


def test_deadline_waits_for_synchronous_invocation_before_indeterminate(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        started = Event()
        release = Event()
        counter = _Counter()

        def delayed_add(amount: int) -> int:
            started.set()
            release.wait()
            return counter.add(amount)

        descriptor = _descriptor("add", deadline_seconds=0.02)
        adapter = ComponentAdapter(
            (
                ActionBinding(
                    descriptor,
                    lambda payload: ((int(payload["amount"]),), {}),
                    lambda value: int(cast(int, value)),
                    invoke=delayed_add,
                ),
            )
        )
        runtime, endpoint, _ = await _compose(tmp_path / "deadline.sqlite", adapter)
        message_id = uuid4()
        request = asyncio.create_task(
            endpoint.request(
                descriptor.action_ref(),
                {"amount": 2},
                target=runtime.address_for("target"),
                timeout_seconds=0.2,
                message_id=message_id,
            )
        )
        assert await asyncio.to_thread(started.wait, 1)
        await asyncio.sleep(0.05)
        before_release = await runtime.lookup_message_outcome(message_id)
        assert before_release is not None
        assert before_release.request_receipt.status.value == "delivering"
        assert counter.value == 0
        assert runtime.health is RuntimeHealth.QUIESCING
        release.set()
        with pytest.raises(RuntimeRequestTimedOut):
            await request
        after_release = None
        for _ in range(100):
            after_release = await runtime.lookup_message_outcome(message_id)
            if (
                after_release is not None
                and after_release.request_receipt.status.value == "indeterminate"
            ):
                break
            await asyncio.sleep(0.01)
        assert counter.value == 2
        assert after_release is not None
        assert after_release.request_receipt.status.value == "indeterminate"
        assert runtime.health is RuntimeHealth.RECOVERY_REQUIRED
        await runtime.aclose()

    asyncio.run(exercise())


def test_deadline_compensation_holds_quiescing_then_aborts_safely(tmp_path: Path) -> None:
    async def exercise() -> None:
        compensation_started = Event()
        release_compensation = Event()
        descriptor = _descriptor("coordinate", deadline_seconds=0.02)

        async def coordinate(
            _args: tuple[object, ...],
            _kwargs: dict[str, object],
            _execution: ComponentExecution,
        ) -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError as error:
                compensation_started.set()
                await asyncio.to_thread(release_compensation.wait)
                raise RuntimeComponentDeadlineExceeded("coordinate") from error

        adapter = ComponentAdapter(
            (
                ActionBinding(
                    descriptor,
                    lambda _payload: ((), {}),
                    lambda value: value,
                    handler=coordinate,
                ),
            )
        )
        runtime, endpoint, _ = await _compose(tmp_path / "deadline-abort.sqlite", adapter)
        request = asyncio.create_task(
            endpoint.request(
                descriptor.action_ref(),
                {},
                target=runtime.address_for("target"),
                timeout_seconds=1,
            )
        )
        assert await asyncio.to_thread(compensation_started.wait, 1)
        assert runtime.health is RuntimeHealth.QUIESCING
        assert not request.done()

        release_compensation.set()
        outcome = await request
        assert outcome.response.kind.value == "fault"
        assert outcome.response.payload.value["type"] == "RuntimeComponentDeadlineExceeded"
        assert outcome.trace_disposition is RuntimeTraceDisposition.ABORTED
        assert runtime.health is RuntimeHealth.READY
        await runtime.aclose()

    asyncio.run(exercise())


def test_failed_deadline_compensation_requires_recovery(tmp_path: Path) -> None:
    async def exercise() -> None:
        descriptor = _descriptor("coordinate", deadline_seconds=0.02)

        async def coordinate(
            _args: tuple[object, ...],
            _kwargs: dict[str, object],
            _execution: ComponentExecution,
        ) -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError as error:
                raise RuntimeError("compensation failed") from error

        adapter = ComponentAdapter(
            (
                ActionBinding(
                    descriptor,
                    lambda _payload: ((), {}),
                    lambda value: value,
                    handler=coordinate,
                ),
            )
        )
        runtime, endpoint, _ = await _compose(tmp_path / "deadline-failed.sqlite", adapter)
        outcome = await endpoint.request(
            descriptor.action_ref(),
            {},
            target=runtime.address_for("target"),
            timeout_seconds=1,
        )
        assert outcome.response.kind.value == "fault"
        assert outcome.response.payload.value["type"] == "RuntimeError"
        assert outcome.trace_disposition is RuntimeTraceDisposition.INDETERMINATE
        assert runtime.health is RuntimeHealth.RECOVERY_REQUIRED
        await runtime.aclose()

    asyncio.run(exercise())


def test_signals_close_by_acknowledgement(tmp_path: Path) -> None:
    async def exercise() -> None:
        seen = asyncio.Event()

        async def signal(
            _args: tuple[object, ...], _kwargs: dict[str, object], execution: ComponentExecution
        ) -> None:
            seen.set()
            await execution.ack()

        adapter = ComponentAdapter(
            (
                ActionBinding(
                    _descriptor("add"),
                    lambda _payload: ((), {}),
                    lambda value: value,
                    handler=signal,
                ),
            )
        )
        runtime, endpoint, _ = await _compose(tmp_path / "signal.sqlite", adapter)
        receipt = await endpoint.signal(
            _descriptor("add").action_ref(), {}, target=runtime.address_for("target")
        )
        await asyncio.wait_for(seen.wait(), 1)
        facts = ()
        for _ in range(100):
            facts = (
                await runtime.query_history(RuntimeHistoryQuery(message_id=receipt.message_id))
            ).facts
            if any(fact.fact_type == "trace_committed" for fact in facts):
                break
            await asyncio.sleep(0.01)
        assert any(fact.fact_type == "trace_committed" for fact in facts)
        await runtime.aclose()

    asyncio.run(exercise())


def test_history_is_cursor_paginated_and_filterable(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime, endpoint, _ = await _compose(
            tmp_path / "history.sqlite", _counter_adapter(_Counter())
        )
        outcome = await endpoint.request(
            _descriptor("add").action_ref(), {"amount": 1}, target=runtime.address_for("target")
        )
        first = await runtime.query_history(
            RuntimeHistoryQuery(trace_id=outcome.request.trace_id, limit=2)
        )
        assert len(first.facts) == 2 and first.next_position is not None
        second = await runtime.query_history(
            RuntimeHistoryQuery(
                trace_id=outcome.request.trace_id, after_position=first.next_position, limit=100
            )
        )
        assert second.facts
        assert await runtime.count_history(
            RuntimeHistoryQuery(trace_id=outcome.request.trace_id)
        ) == len(first.facts) + len(second.facts)
        summaries = await runtime.query_trace_summaries(
            limit=1,
            root_action_ids=("component.test.counter.add",),
        )
        assert len(summaries.summaries) == 1
        assert summaries.summaries[0].trace_id == outcome.request.trace_id
        assert summaries.summaries[0].terminal_position == outcome.terminal_position
        assert await runtime.current_position() >= outcome.terminal_position
        await runtime.aclose()

    asyncio.run(exercise())


def test_topology_is_atomic_and_identity_is_durable(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "identity.sqlite"
        runtime, _endpoint, manifest = await _compose(path, _counter_adapter(_Counter()))
        identity = runtime.address_for("target")
        await runtime.aclose()
        reopened = SqliteMessageRuntime(path, runtime_key="test.runtime")
        await reopened.prepare_static_topology(manifest)
        assert reopened.address_for("target") == identity
        changed = replace(manifest, occurrences=manifest.occurrences[:-1], manifest_hash="")
        changed = replace(changed, manifest_hash=topology_manifest_hash(changed))
        with pytest.raises(RuntimeRegistrationInvalid):
            await reopened.prepare_static_topology(changed)
        await reopened.aclose()

    asyncio.run(exercise())


def test_restart_marks_open_delivery_indeterminate(tmp_path: Path) -> None:
    async def exercise() -> None:
        started = asyncio.Event()

        async def hang(
            _args: tuple[object, ...], _kwargs: dict[str, object], _execution: ComponentExecution
        ) -> None:
            started.set()
            await asyncio.Event().wait()

        adapter = ComponentAdapter(
            (
                ActionBinding(
                    _descriptor("add"), lambda _payload: ((), {}), lambda value: value, handler=hang
                ),
            )
        )
        path = tmp_path / "open.sqlite"
        runtime, endpoint, _ = await _compose(path, adapter)
        task = asyncio.create_task(
            endpoint.request(
                _descriptor("add").action_ref(), {}, target=runtime.address_for("target")
            )
        )
        await asyncio.wait_for(started.wait(), 1)
        await runtime.aclose()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        reopened = SqliteMessageRuntime(path, runtime_key="test.runtime")
        assert reopened.health is RuntimeHealth.RECOVERY_REQUIRED
        facts = (
            await reopened.query_history(RuntimeHistoryQuery(fact_type="delivery_indeterminate"))
        ).facts
        assert facts
        await reopened.aclose()

    asyncio.run(exercise())


def test_lane_fifo_cross_lane_overlap_and_writer_preference(tmp_path: Path) -> None:
    async def exercise() -> None:
        first_reader_started = Event()
        second_reader_started = Event()
        release_first_reader = Event()
        writer_started = Event()
        release_writer = Event()
        independent_a_started = Event()
        independent_b_started = Event()
        release_independent = Event()
        fifo_first_started = Event()
        fifo_second_started = Event()
        release_fifo_first = Event()

        async def read(
            args: tuple[object, ...],
            _kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            label = str(args[0])
            if label == "first":
                first_reader_started.set()
                await asyncio.to_thread(release_first_reader.wait)
            else:
                second_reader_started.set()
            await execution.complete(label)

        async def write(
            _args: tuple[object, ...],
            _kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            writer_started.set()
            await asyncio.to_thread(release_writer.wait)
            await execution.complete("written")

        async def independent(
            args: tuple[object, ...],
            _kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            (independent_a_started if args[0] == "a" else independent_b_started).set()
            await asyncio.to_thread(release_independent.wait)
            await execution.complete(args[0])

        async def fifo(
            args: tuple[object, ...],
            _kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            if args[0] == "first":
                fifo_first_started.set()
                await asyncio.to_thread(release_fifo_first.wait)
            else:
                fifo_second_started.set()
            await execution.complete(args[0])

        def decode_label(payload: JsonObject) -> tuple[tuple[object, ...], dict[str, object]]:
            return (str(payload["label"]),), {}

        read_descriptor = _descriptor("read", lane="read", group="state", access="shared")
        write_descriptor = _descriptor("write", lane="write", group="state", access="exclusive")
        independent_a = _descriptor("independent_a", lane="independent_a")
        independent_b = _descriptor("independent_b", lane="independent_b")
        fifo_descriptor = _descriptor("fifo", lane="fifo")
        adapter = ComponentAdapter(
            (
                ActionBinding(read_descriptor, decode_label, lambda value: value, handler=read),
                ActionBinding(
                    write_descriptor,
                    lambda _payload: ((), {}),
                    lambda value: value,
                    handler=write,
                ),
                ActionBinding(
                    independent_a, decode_label, lambda value: value, handler=independent
                ),
                ActionBinding(
                    independent_b, decode_label, lambda value: value, handler=independent
                ),
                ActionBinding(fifo_descriptor, decode_label, lambda value: value, handler=fifo),
            )
        )
        runtime, endpoint, _ = await _compose(
            tmp_path / "lanes.sqlite",
            adapter,
            lanes=(
                RuntimeLaneDeclaration("read", worker_limit=2),
                RuntimeLaneDeclaration("write"),
                RuntimeLaneDeclaration("independent_a"),
                RuntimeLaneDeclaration("independent_b"),
                RuntimeLaneDeclaration("fifo"),
            ),
        )
        target = runtime.address_for("target")

        overlap_a = asyncio.create_task(
            endpoint.request(independent_a.action_ref(), {"label": "a"}, target=target)
        )
        overlap_b = asyncio.create_task(
            endpoint.request(independent_b.action_ref(), {"label": "b"}, target=target)
        )
        assert await asyncio.to_thread(independent_a_started.wait, 1)
        assert await asyncio.to_thread(independent_b_started.wait, 1)
        release_independent.set()
        await asyncio.wait_for(asyncio.gather(overlap_a, overlap_b), 1)

        fifo_first = asyncio.create_task(
            endpoint.request(fifo_descriptor.action_ref(), {"label": "first"}, target=target)
        )
        assert await asyncio.to_thread(fifo_first_started.wait, 1)
        fifo_second = asyncio.create_task(
            endpoint.request(fifo_descriptor.action_ref(), {"label": "second"}, target=target)
        )
        await asyncio.sleep(0.02)
        assert not fifo_second_started.is_set()
        release_fifo_first.set()
        await asyncio.wait_for(asyncio.gather(fifo_first, fifo_second), 1)
        assert fifo_second_started.is_set()

        first_reader = asyncio.create_task(
            endpoint.request(read_descriptor.action_ref(), {"label": "first"}, target=target)
        )
        assert await asyncio.to_thread(first_reader_started.wait, 1)
        writer = asyncio.create_task(
            endpoint.request(write_descriptor.action_ref(), {}, target=target)
        )
        await asyncio.sleep(0.02)
        second_reader = asyncio.create_task(
            endpoint.request(read_descriptor.action_ref(), {"label": "second"}, target=target)
        )
        await asyncio.sleep(0.02)
        assert not writer_started.is_set()
        assert not second_reader_started.is_set()
        release_first_reader.set()
        assert await asyncio.to_thread(writer_started.wait, 1)
        assert not second_reader_started.is_set()
        release_writer.set()
        await asyncio.wait_for(asyncio.gather(first_reader, writer, second_reader), 1)
        assert second_reader_started.is_set()
        await runtime.aclose()

    asyncio.run(exercise())


def test_completion_and_acknowledgement_are_exactly_once(tmp_path: Path) -> None:
    async def exercise() -> None:
        duplicate_completion_rejected = Event()
        duplicate_ack_rejected = Event()

        async def handler(
            _args: tuple[object, ...],
            _kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            if execution.request.kind.value == "signal":
                await execution.ack()
                with pytest.raises(RuntimeDeliveryUnknown):
                    await execution.ack()
                duplicate_ack_rejected.set()
                return
            await execution.complete("done")
            with pytest.raises(RuntimeDeliveryUnknown):
                await execution.complete("again")
            duplicate_completion_rejected.set()

        descriptor = _descriptor("add")
        adapter = ComponentAdapter(
            (
                ActionBinding(
                    descriptor,
                    lambda _payload: ((), {}),
                    lambda value: value,
                    handler=handler,
                ),
            )
        )
        runtime, endpoint, _ = await _compose(tmp_path / "exactly-once.sqlite", adapter)
        target = runtime.address_for("target")
        await endpoint.request(descriptor.action_ref(), {}, target=target)
        signal = await endpoint.signal(descriptor.action_ref(), {}, target=target)
        assert await asyncio.to_thread(duplicate_completion_rejected.wait, 1)
        assert await asyncio.to_thread(duplicate_ack_rejected.wait, 1)
        facts = (
            await runtime.query_history(RuntimeHistoryQuery(message_id=signal.message_id))
        ).facts
        assert sum(fact.fact_type == "delivery_completed" for fact in facts) == 1
        await runtime.aclose()

    asyncio.run(exercise())


def test_caller_timeout_does_not_cancel_execution_and_outcome_is_queryable(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        started = Event()
        release = Event()
        calls = 0

        async def handler(
            _args: tuple[object, ...],
            _kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            nonlocal calls
            calls += 1
            started.set()
            await asyncio.to_thread(release.wait)
            await execution.complete("eventual")

        descriptor = _descriptor("add")
        adapter = ComponentAdapter(
            (
                ActionBinding(
                    descriptor,
                    lambda _payload: ((), {}),
                    lambda value: value,
                    handler=handler,
                ),
            )
        )
        runtime, endpoint, _ = await _compose(tmp_path / "timeout.sqlite", adapter)
        message_id = uuid4()
        request = asyncio.create_task(
            endpoint.request(
                descriptor.action_ref(),
                {},
                target=runtime.address_for("target"),
                timeout_seconds=0.02,
                message_id=message_id,
            )
        )
        assert await asyncio.to_thread(started.wait, 1)
        with pytest.raises(RuntimeRequestTimedOut) as raised:
            await request
        assert raised.value.message_id == message_id
        assert calls == 1
        release.set()
        durable = None
        for _ in range(100):
            durable = await runtime.lookup_message_outcome(message_id)
            if durable is not None and durable.terminal_envelope is not None:
                break
            await asyncio.sleep(0.01)
        assert durable is not None
        assert durable.terminal_envelope is not None
        assert durable.terminal_envelope.payload.value == {"result": "eventual"}
        outcome = await endpoint.request(
            descriptor.action_ref(),
            {},
            target=runtime.address_for("target"),
            message_id=message_id,
        )
        assert outcome.response.payload.value == {"result": "eventual"}
        assert calls == 1
        await runtime.aclose()

    asyncio.run(exercise())


def test_reconstruction_requires_effect_and_commit_within_cursor(tmp_path: Path) -> None:
    async def exercise() -> None:
        counter = _Counter()
        runtime, endpoint, _ = await _compose(
            tmp_path / "cursor.sqlite",
            _replayable_counter_adapter(counter),
            replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
        )
        outcome = await endpoint.request(
            _descriptor("add", replay=RuntimeReplayMode.CANONICAL_EFFECT).action_ref(),
            {"amount": 4},
            target=runtime.address_for("target"),
        )
        effects = (
            await runtime.query_history(
                RuntimeHistoryQuery(
                    trace_id=outcome.request.trace_id,
                    fact_type="canonical_effect",
                )
            )
        ).facts
        assert len(effects) == 1
        effect_cursor = effects[0].runtime_position
        assert effect_cursor < outcome.terminal_position

        report = await runtime.reconstruct(
            RuntimeReconstructionRequest(
                through_position=effect_cursor,
                reset_targets=True,
            )
        )
        assert report.applied_effects == 0
        assert counter.value == 0
        assert runtime.health is RuntimeHealth.BRANCH_PENDING
        await runtime.aclose()

    asyncio.run(exercise())


def test_superseding_aggregate_replays_referenced_child_effects_and_validates_digest(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        counter = _Counter()
        child_descriptor = _descriptor("add", replay=RuntimeReplayMode.CANONICAL_EFFECT)
        parent_descriptor = _descriptor("coordinate", replay=RuntimeReplayMode.COORDINATOR_TRACE)

        async def coordinate(
            _args: tuple[object, ...],
            kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            await execution.call(
                "child-add",
                child_descriptor.action_ref(),
                {"amount": int(cast(int, kwargs["amount"]))},
                target=execution.address_for("child"),
            )
            reference = await execution.effect_reference("child-add")
            if bool(kwargs.get("corrupt_digest")):
                reference = RuntimeCanonicalEffectReference(
                    reference.request_message_id,
                    "0" * 64,
                )
            await execution.complete(
                counter.value,
                canonical_effect=execution.superseding_aggregate_effect((reference,)),
            )

        child = _replayable_counter_adapter(counter)
        parent = ComponentAdapter(
            (
                ActionBinding(
                    parent_descriptor,
                    lambda payload: (
                        (),
                        {
                            "amount": payload["amount"],
                            "corrupt_digest": payload.get("corrupt_digest", False),
                        },
                    ),
                    lambda value: value,
                    handler=coordinate,
                ),
            )
        )
        ingress = ComponentAdapter(
            binding_id="binding.test.ingress",
            component_contract_id="component.test.ingress",
        )
        runtime = SqliteMessageRuntime(tmp_path / "aggregate.sqlite", runtime_key="test.runtime")
        declarations = (
            ComponentOccurrenceDeclaration(
                "child",
                _CONTRACT,
                _BINDING,
                1,
                replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
            ),
            ComponentOccurrenceDeclaration("parent", _CONTRACT, _BINDING, 1),
            ComponentOccurrenceDeclaration(
                "ingress", "component.test.ingress", "binding.test.ingress", 1
            ),
        )
        manifest = RuntimeTopologyManifest("test.runtime", 4, declarations, (), "")
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        await runtime.prepare_static_topology(manifest)
        registrations = [await runtime.register_occurrence(item) for item in declarations]
        await runtime.attach_participant(registrations[0], child, child.describe().actions)
        await runtime.attach_participant(registrations[1], parent, parent.describe().actions)
        await runtime.attach_participant(registrations[2], ingress)
        await runtime.confirm_static_topology(manifest)
        endpoint = ComponentEndpoint(runtime, ingress, source=runtime.address_for("ingress"))

        await endpoint.request(
            parent_descriptor.action_ref(),
            {"amount": 5},
            target=runtime.address_for("parent"),
        )
        assert counter.value == 5
        report = await runtime.reconstruct(RuntimeReconstructionRequest(reset_targets=True))
        assert report.applied_effects == 1
        assert counter.value == 5

        await endpoint.request(
            parent_descriptor.action_ref(),
            {"amount": 1, "corrupt_digest": True},
            target=runtime.address_for("parent"),
        )
        with pytest.raises(RuntimeReplayIncompatible, match="digest differs"):
            await runtime.reconstruct(RuntimeReconstructionRequest(reset_targets=True))
        await runtime.aclose()

    asyncio.run(exercise())


def test_reconstruction_preflight_rejection_preserves_ready_health(tmp_path: Path) -> None:
    async def exercise() -> None:
        counter = _Counter()
        runtime, endpoint, _ = await _compose(
            tmp_path / "preflight.sqlite",
            _replayable_counter_adapter(counter),
            replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
        )
        await endpoint.request(
            _descriptor("add", replay=RuntimeReplayMode.CANONICAL_EFFECT).action_ref(),
            {"amount": 1},
            target=runtime.address_for("target"),
        )
        with pytest.raises(RuntimeReplayTargetNotPrepared):
            await runtime.reconstruct(RuntimeReconstructionRequest())
        assert runtime.health is RuntimeHealth.READY
        await runtime.aclose()

    asyncio.run(exercise())


def test_checkpoint_reconstruction_requires_one_common_cursor(tmp_path: Path) -> None:
    async def compose(path: Path) -> tuple[SqliteMessageRuntime, _Counter, _Counter]:
        runtime = SqliteMessageRuntime(path, runtime_key="checkpoint.test")
        left_counter, right_counter = _Counter(), _Counter()
        left = _replayable_counter_adapter(left_counter)
        right = _replayable_counter_adapter(right_counter)
        declarations = tuple(
            ComponentOccurrenceDeclaration(
                key,
                _CONTRACT,
                _BINDING,
                1,
                replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
            )
            for key in ("left", "right")
        )
        manifest = RuntimeTopologyManifest("checkpoint.test", 4, declarations, (), "")
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        await runtime.prepare_static_topology(manifest)
        for declaration, participant in zip(declarations, (left, right), strict=True):
            registration = await runtime.register_occurrence(declaration)
            await runtime.attach_participant(
                registration,
                participant,
                participant.describe().actions,
            )
        await runtime.confirm_static_topology(manifest)
        return runtime, left_counter, right_counter

    async def exercise() -> None:
        valid, _left, _right = await compose(tmp_path / "valid-checkpoints.sqlite")
        report = await valid.reconstruct(
            RuntimeReconstructionRequest(
                checkpoint_references={"left": "checkpoint:2", "right": "checkpoint:2"}
            )
        )
        assert report.start_position == 2
        assert report.verified is True
        await valid.aclose()

        invalid, _left, _right = await compose(tmp_path / "invalid-checkpoints.sqlite")
        with pytest.raises(RuntimeReplayIncompatible):
            await invalid.reconstruct(
                RuntimeReconstructionRequest(
                    checkpoint_references={
                        "left": "checkpoint:2",
                        "right": "checkpoint:3",
                    }
                )
            )
        assert invalid.health is RuntimeHealth.RECOVERY_REQUIRED
        await invalid.aclose()

    asyncio.run(exercise())


def test_reconstruction_failure_after_partial_reset_requires_recovery(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = SqliteMessageRuntime(tmp_path / "partial-reset.sqlite", runtime_key="reset.test")
        left_state = {"value": 1}
        right_state = {"value": 1}

        def fail_reset() -> None:
            raise RuntimeError("right reset failed")

        left = ComponentAdapter(
            binding_id="binding.test.left",
            component_contract_id="component.test.left",
            replay_state=ReplayStateBinding(
                is_empty=lambda: left_state["value"] == 0,
                reset=lambda: left_state.update(value=0),
                import_checkpoint=lambda _reference: 0,
                export_state=lambda: left_state,
            ),
        )
        right = ComponentAdapter(
            binding_id="binding.test.right",
            component_contract_id="component.test.right",
            replay_state=ReplayStateBinding(
                is_empty=lambda: right_state["value"] == 0,
                reset=fail_reset,
                import_checkpoint=lambda _reference: 0,
                export_state=lambda: right_state,
            ),
        )
        declarations = (
            ComponentOccurrenceDeclaration(
                "left",
                "component.test.left",
                "binding.test.left",
                1,
                replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
            ),
            ComponentOccurrenceDeclaration(
                "right",
                "component.test.right",
                "binding.test.right",
                1,
                replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
            ),
        )
        manifest = RuntimeTopologyManifest("reset.test", 4, declarations, (), "")
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        await runtime.prepare_static_topology(manifest)
        for declaration, participant in zip(declarations, (left, right), strict=True):
            registration = await runtime.register_occurrence(declaration)
            await runtime.attach_participant(registration, participant)
        await runtime.confirm_static_topology(manifest)

        with pytest.raises(RuntimeError, match="right reset failed"):
            await runtime.reconstruct(RuntimeReconstructionRequest(reset_targets=True))

        assert left_state["value"] == 0
        assert right_state["value"] == 1
        assert runtime.health is RuntimeHealth.RECOVERY_REQUIRED
        await runtime.aclose()

    asyncio.run(exercise())


def test_external_boundaries_are_reported_without_replay_invocation(tmp_path: Path) -> None:
    async def exercise() -> None:
        invoked = False

        def replay_should_not_run(_effect: JsonObject) -> None:
            nonlocal invoked
            invoked = True

        descriptor = _descriptor("external", replay=RuntimeReplayMode.EXTERNAL_EXCHANGE)
        external = ComponentAdapter(
            (
                ActionBinding(
                    descriptor,
                    lambda payload: ((payload,), {}),
                    lambda value: value,
                    invoke=lambda value: value,
                    apply_replay_effect=replay_should_not_run,
                ),
            )
        )
        runtime = SqliteMessageRuntime(tmp_path / "external.sqlite", runtime_key="external.test")
        declaration = ComponentOccurrenceDeclaration(
            "external.api",
            _CONTRACT,
            _BINDING,
            1,
            replay_authority=RuntimeReplayMode.EXTERNAL_EXCHANGE,
        )
        manifest = RuntimeTopologyManifest("external.test", 4, (declaration,), (), "")
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        await runtime.prepare_static_topology(manifest)
        registration = await runtime.register_occurrence(declaration)
        await runtime.attach_participant(registration, external, external.describe().actions)
        await runtime.confirm_static_topology(manifest)
        report = await runtime.reconstruct(
            RuntimeReconstructionRequest(
                external_boundaries=(
                    RuntimeExternalBoundaryDisposition(
                        "external.api",
                        RuntimeExternalBoundaryMode.LIVE,
                    ),
                )
            )
        )
        assert invoked is False
        assert report.external_boundaries[0].mode is RuntimeExternalBoundaryMode.LIVE
        await runtime.aclose()

    asyncio.run(exercise())


def test_get_trace_has_no_one_thousand_fact_cap(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime, endpoint, _ = await _compose(
            tmp_path / "large-trace.sqlite",
            _counter_adapter(_Counter()),
        )
        outcome = await endpoint.request(
            _descriptor("add").action_ref(),
            {"amount": 1},
            target=runtime.address_for("target"),
        )
        durable = await runtime.lookup_message_outcome(outcome.request.message_id)
        assert durable is not None
        for index in range(1001):
            runtime._append_fact(  # noqa: SLF001 - contract stress fixture
                "trace_diagnostic",
                envelope=durable.request_envelope,
                details={"index": index},
            )
        trace = await runtime.get_trace(outcome.request.trace_id)
        assert len(trace.facts) > 1000
        assert sum(fact.fact_type == "trace_diagnostic" for fact in trace.facts) == 1001
        await runtime.aclose()

    asyncio.run(exercise())


def test_invalid_curated_operation_prevents_topology_confirmation(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = SqliteMessageRuntime(tmp_path / "invalid-topology.sqlite", runtime_key="bad")
        target_adapter = _counter_adapter(_Counter())
        occurrence = ComponentOccurrenceDeclaration("target", _CONTRACT, _BINDING, 1)
        operation = RuntimeCuratedOperationDeclaration(
            operation_id="bad.operation",
            target_instance_key="target",
            component_contract_id=_CONTRACT,
            action_id=f"{_CONTRACT}.missing",
            schema_version=1,
            binding_id=_BINDING,
            binding_version=1,
            request_codec_id="codec.test.missing.request.json",
            request_codec_version=1,
            request_payload_disposition=RuntimePayloadDisposition.COMMAND,
            result_payload_disposition=RuntimePayloadDisposition.QUERY_RESULT,
            fault_payload_disposition=RuntimePayloadDisposition.DIAGNOSTIC,
        )
        manifest = RuntimeTopologyManifest("bad", 4, (occurrence,), (operation,), "")
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        await runtime.prepare_static_topology(manifest)
        registration = await runtime.register_occurrence(occurrence)
        await runtime.attach_participant(
            registration,
            target_adapter,
            target_adapter.describe().actions,
        )
        with pytest.raises(RuntimeRegistrationInvalid):
            await runtime.confirm_static_topology(manifest)
        assert runtime.health is RuntimeHealth.STARTING
        await runtime.aclose()

    asyncio.run(exercise())


def test_replay_state_spi_is_available_to_runtime() -> None:
    state = {"value": 1}
    adapter = ComponentAdapter(
        (
            ActionBinding(
                _descriptor("add"),
                lambda _payload: ((), {}),
                lambda value: value,
                invoke=lambda: None,
            ),
        ),
        replay_state=ReplayStateBinding(
            is_empty=lambda: state["value"] == 0,
            reset=lambda: state.update(value=0),
            import_checkpoint=lambda _reference: 2,
            export_state=lambda: state,
            verify=lambda: (),
        ),
    )

    async def exercise() -> None:
        assert not (await adapter.replay_state_status()).empty
        await adapter.reset_replay_state()
        assert (await adapter.replay_state_status()).empty
        assert await adapter.import_replay_checkpoint("checkpoint") == 2
        assert len(await adapter.replay_state_digest()) == 64
        assert await adapter.verify_replay_state() == ()

    asyncio.run(exercise())


def test_branch_provenance_requires_matching_reconstruction(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime, _endpoint, _ = await _compose(
            tmp_path / "branch.sqlite", _counter_adapter(_Counter())
        )
        with pytest.raises(RuntimeReplayIncompatible):
            await runtime.record_branch_provenance(
                source_runtime_id=UUID(int=0), source_cursor=0, verified_digest="0" * 64
            )
        await runtime.aclose()

    asyncio.run(exercise())
