from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from components.rtg.graph import InMemoryRtgGraph, RtgAnchor, RtgGraphObjectNotFound
from components.rtg.graph.runtime_binding import create_rtg_graph_adapter, create_rtg_graph_proxy
from components.runtime.component_adapter import (
    ActionBinding,
    ExplicitComponentAdapter,
    ReplayStateBinding,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeClient,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import (
    ComponentOccurrenceDeclaration,
    JsonObject,
    JsonValue,
    RuntimeActionUnknown,
    RuntimeAddress,
    RuntimeAddressUnknown,
    RuntimeCuratedOperationDeclaration,
    RuntimeDeliveryStatus,
    RuntimeExternalBoundaryDisposition,
    RuntimeExternalBoundaryMode,
    RuntimeFailStopped,
    RuntimeHistoryQuery,
    RuntimeLedgerUnavailable,
    RuntimeMessageConflict,
    RuntimeMessageKind,
    RuntimeReconstructionRequest,
    RuntimeRegistrationInvalid,
    RuntimeReplayIncompatible,
    RuntimeReplayMode,
    RuntimeReplayTargetNotPrepared,
    RuntimeRequestOutcome,
    RuntimeRequestTimedOut,
    RuntimeSchemaUnsupported,
    RuntimeTopologyManifest,
    RuntimeTraceDisposition,
    SqliteMessageRuntime,
)

MODEL_EVIDENCE = {
    "MessageRuntimeBoundaryVerification": (
        "test_runtime_creates_ledger_parent_for_a_fresh_data_root",
        "test_durable_acceptance_duplicate_protection_and_history",
        "test_same_type_occurrences_are_isolated",
        "test_restart_preserves_identity_and_reconstructs_committed_effects",
        "test_terminal_persistence_failure_enters_fail_stop",
        "test_post_effect_terminal_encoding_failure_enters_fail_stop",
        "test_fail_stop_quiesces_already_accepted_queued_deliveries",
        "test_runtime_dispatches_the_durable_canonical_payload_copy",
        "test_recorded_external_response_is_supplied_without_a_live_collaborator",
        "test_final_aggregate_effect_supersedes_derived_effects_in_its_trace",
        "test_root_trace_waits_for_nested_signal_before_committing",
        "test_nested_signal_uncertainty_marks_trace_and_runtime_recovery_required",
        "test_post_terminal_causal_signal_is_rejected_without_poisoning_replay",
        "test_recovery_ingress_reserves_one_root_until_its_trace_finishes",
    ),
    "RegisterComponentOccurrenceContractVerification": (
        "test_restart_preserves_identity_and_reconstructs_committed_effects",
        "test_confirmed_topology_rejects_new_occurrence_without_durable_insertion",
    ),
    "PrepareStaticRuntimeTopologyContractVerification": (
        "test_confirmed_topology_rejects_new_occurrence_without_durable_insertion",
        "test_interrupted_first_start_retries_only_the_prepared_topology",
    ),
    "ConfirmStaticRuntimeTopologyContractVerification": (
        "test_static_topology_requires_exact_manifest_inventory",
        "test_static_topology_rejects_curated_operation_without_adapter_target",
        "test_interrupted_first_start_retries_only_the_prepared_topology",
    ),
    "SendRuntimeMessageContractVerification": ("test_initial_append_failure_prevents_dispatch",),
    "RequestRuntimeMessageContractVerification": ("test_timeout_does_not_cancel_or_redeliver",),
    "QueryRuntimeHistoryContractVerification": ("test_history_is_cursor_paginated_and_filterable",),
    "GetRuntimeCausalTraceContractVerification": (
        "test_history_is_cursor_paginated_and_filterable",
    ),
    "ReconstructRuntimeStateContractVerification": (
        "test_restart_preserves_identity_and_reconstructs_committed_effects",
        "test_reconstruction_requires_empty_reset_checkpoint_or_confirmed_state",
        "test_reconstruction_rejects_a_canonical_effect_with_a_changed_digest",
        "test_recorded_external_response_is_supplied_without_a_live_collaborator",
        "test_final_aggregate_effect_supersedes_derived_effects_in_its_trace",
        "test_checkpoint_digest_is_verified_before_later_effects",
        "test_replay_verification_may_use_runtime_messages_without_growing_history",
        "test_root_coordinator_may_initiate_reconstruction_as_only_pending_delivery",
        "test_historical_reconstruction_requires_durable_branch_provenance_before_ingress",
    ),
    "RecordRuntimeBranchProvenanceContractVerification": (
        "test_historical_reconstruction_requires_durable_branch_provenance_before_ingress",
    ),
    "ReplayStateStatusContractVerification": (
        "test_reconstruction_requires_empty_reset_checkpoint_or_confirmed_state",
    ),
    "ResetReplayStateContractVerification": (
        "test_reconstruction_requires_empty_reset_checkpoint_or_confirmed_state",
    ),
    "ImportReplayCheckpointContractVerification": (
        "test_reconstruction_requires_empty_reset_checkpoint_or_confirmed_state",
        "test_checkpoint_digest_is_verified_before_later_effects",
    ),
    "ReplayStateDigestContractVerification": (
        "test_reconstruction_requires_empty_reset_checkpoint_or_confirmed_state",
        "test_checkpoint_digest_is_verified_before_later_effects",
    ),
    "VerifyReplayStateContractVerification": (
        "test_reconstruction_requires_empty_reset_checkpoint_or_confirmed_state",
        "test_replay_verification_may_use_runtime_messages_without_growing_history",
    ),
}


class _Counter:
    def __init__(self, *, delay: float = 0) -> None:
        self.value = 0
        self.calls = 0
        self.delay = delay
        self.call_order: list[int] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def increment(self, amount: int) -> int:
        with self._lock:
            self.calls += 1
            self.call_order.append(amount)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            with self._lock:
                self.value += amount
                return self.value
        finally:
            with self._lock:
                self.active -= 1

    def reset(self) -> None:
        with self._lock:
            self.value = 0

    def import_checkpoint(self, reference: str) -> int:
        cursor, value = reference.split(":", maxsplit=1)
        with self._lock:
            self.value = int(value)
        return int(cursor)


class _ExpectedFailure(Exception):
    pass


def _counter_adapter(
    counter: _Counter,
    *,
    max_in_flight: int = 1,
    confirmed_cursor: int | None = None,
    invalid_checkpoint_digest: bool = False,
) -> ExplicitComponentAdapter:
    confirmed = [confirmed_cursor]
    confirmed_digest = [
        _counter_state_digest(counter) if confirmed_cursor is not None else None
    ]

    def reset() -> None:
        counter.reset()
        confirmed[0] = None
        confirmed_digest[0] = None

    def import_checkpoint(reference: str) -> int:
        cursor = counter.import_checkpoint(reference)
        confirmed[0] = cursor
        confirmed_digest[0] = (
            "0" * 64 if invalid_checkpoint_digest else _counter_state_digest(counter)
        )
        return cursor

    descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.counter",
        action_id="component.test.counter.increment",
        binding_id="binding.test.counter.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.counter.request.json",
        result_codec_id="codec.test.counter.result.json",
        failure_codec_id="codec.test.counter.failure.json",
        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
        replay_mode=RuntimeReplayMode.CANONICAL_EFFECT,
        concurrency_lane="serialized" if max_in_flight == 1 else "parallel",
        max_in_flight=max_in_flight,
    )
    return ExplicitComponentAdapter(
        (
            ActionBinding(
                descriptor=descriptor,
                invoke=counter.increment,
                decode_request=lambda payload: ((cast(int, payload["amount"]),), {}),
                encode_result=encode_json,
                build_replay_effect=lambda args, _kwargs, _result: {"amount": cast(int, args[0])},
                apply_replay_effect=lambda payload: counter.increment(cast(int, payload["amount"])),
            ),
        ),
        replay_state=ReplayStateBinding(
            is_empty=lambda: counter.value == 0,
            reset=reset,
            import_checkpoint=import_checkpoint,
            export_state=lambda: {"value": counter.value},
            confirmed_cursor=lambda: confirmed[0],
            confirmed_digest=lambda: confirmed_digest[0],
        ),
    )


def _counter_state_digest(counter: _Counter) -> str:
    encoded = json.dumps({"value": counter.value}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _runtime_and_counter(
    database: Path, *, delay: float = 0
) -> tuple[SqliteMessageRuntime, _Counter, RuntimeClient]:
    runtime = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    counter = _Counter(delay=delay)
    registration = runtime.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(counter),
    )
    address = runtime.address_for(registration.instance_key)
    client = RuntimeClient(
        runtime,
        source=address,
        target=address,
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )
    return runtime, counter, client


def test_durable_acceptance_duplicate_protection_and_history(tmp_path: Path) -> None:
    runtime, counter, client = _runtime_and_counter(tmp_path / "runtime.sqlite")
    try:
        message_id = uuid4()
        envelope = client.envelope(
            "component.test.counter.increment", {"amount": 2}, message_id=message_id
        )
        first = runtime.request_sync(envelope)
        duplicate = runtime.request_sync(envelope)

        assert first.response.payload.value == {"result": 2}
        assert duplicate.terminal_position == first.terminal_position
        assert counter.calls == 1
        facts = runtime.query_history_sync(RuntimeHistoryQuery(message_id=message_id)).facts
        assert [fact.fact_type for fact in facts] == [
            "message_accepted",
            "delivery_started",
            "canonical_effect",
            "trace_committed",
        ]

        with pytest.raises(RuntimeMessageConflict):
            runtime.request_sync(replace(envelope, created_at="changed"))
    finally:
        runtime.close()


def test_initial_append_failure_prevents_dispatch(tmp_path: Path) -> None:
    runtime, counter, client = _runtime_and_counter(tmp_path / "runtime.sqlite")
    try:
        runtime.simulate_ledger_failure_once("message_accepted")
        with pytest.raises(RuntimeLedgerUnavailable):
            client.request_sync("component.test.counter.increment", {"amount": 1})
        assert counter.calls == 0
    finally:
        runtime.close()


def test_static_topology_requires_exact_manifest_inventory(tmp_path: Path) -> None:
    runtime, _, _ = _runtime_and_counter(tmp_path / "runtime.sqlite")
    try:
        declaration = ComponentOccurrenceDeclaration(
            instance_key="test.counter.primary",
            component_contract_id="component.test.counter",
            binding_id="binding.test.counter.v1",
            binding_version=1,
            replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
        )
        manifest = RuntimeTopologyManifest(
            runtime_key="test.runtime",
            manifest_schema_version=1,
            occurrences=(declaration,),
            curated_operations=(
                RuntimeCuratedOperationDeclaration(
                    operation_id="counter.increment",
                    target_instance_key="test.counter.primary",
                    component_contract_id="component.test.counter",
                    action_id="component.test.counter.increment",
                    schema_version=1,
                ),
            ),
            manifest_hash="a" * 64,
        )
        confirmation = runtime.confirm_static_topology_sync(manifest)
        assert confirmation.occurrence_count == 1
        assert len(confirmation.topology_hash) == 64

        refreshed = runtime.confirm_static_topology_sync(
            replace(manifest, manifest_hash="b" * 64)
        )
        assert refreshed.manifest_hash == "b" * 64
        assert refreshed.topology_hash == confirmation.topology_hash

        with pytest.raises(RuntimeRegistrationInvalid, match="contract changed"):
            runtime.confirm_static_topology_sync(
                replace(
                    manifest,
                    occurrences=(replace(declaration, queue_capacity=64),),
                )
            )

        with pytest.raises(RuntimeRegistrationInvalid, match="without migration"):
            runtime.register_source_occurrence(
                instance_key="test.interface.extra",
                component_contract_id="component.test.interface",
                binding_id="binding.test.interface.source.v1",
            )
    finally:
        runtime.close()


def test_confirmed_topology_rejects_new_occurrence_without_durable_insertion(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime, _, _ = _runtime_and_counter(database)
    declaration = ComponentOccurrenceDeclaration(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        binding_id="binding.test.counter.v1",
        binding_version=1,
        replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
    )
    manifest = RuntimeTopologyManifest(
        runtime_key="test.runtime",
        manifest_schema_version=1,
        occurrences=(declaration,),
        curated_operations=(),
        manifest_hash="a" * 64,
    )
    runtime.confirm_static_topology_sync(manifest)
    with pytest.raises(RuntimeRegistrationInvalid, match="without migration"):
        runtime.declare_occurrence(
            ComponentOccurrenceDeclaration(
                instance_key="test.counter.secondary",
                component_contract_id="component.test.counter",
                binding_id="binding.test.counter.v1",
                binding_version=1,
                replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
            )
        )
    with pytest.raises(RuntimeAddressUnknown):
        runtime.address_for("test.counter.secondary")
    runtime.close()

    reopened, _, _ = _runtime_and_counter(database)
    try:
        reopened.confirm_static_topology_sync(manifest)
        with pytest.raises(RuntimeAddressUnknown):
            reopened.address_for("test.counter.secondary")
    finally:
        reopened.close()


def test_interrupted_first_start_retries_only_the_prepared_topology(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite"
    first = ComponentOccurrenceDeclaration(
        instance_key="test.source.first",
        component_contract_id="component.test.source",
        binding_id="binding.test.source.v1",
        binding_version=1,
    )
    second = replace(first, instance_key="test.source.second")
    original = RuntimeTopologyManifest(
        runtime_key="test.partial",
        manifest_schema_version=1,
        occurrences=(first, second),
        curated_operations=(),
        manifest_hash="a" * 64,
    )
    runtime = SqliteMessageRuntime.open(database, runtime_key="test.partial")
    runtime.prepare_static_topology_sync(original)
    first_registration = runtime.declare_occurrence(first)
    runtime.close()

    reopened = SqliteMessageRuntime.open(database, runtime_key="test.partial")
    try:
        different = replace(
            original,
            occurrences=(first, replace(second, instance_key="test.source.other")),
            manifest_hash="b" * 64,
        )
        with pytest.raises(RuntimeRegistrationInvalid, match="durable topology plan"):
            reopened.prepare_static_topology_sync(different)
        with pytest.raises(RuntimeAddressUnknown):
            reopened.address_for("test.source.other")

        reopened.prepare_static_topology_sync(original)
        assert reopened.declare_occurrence(first).instance_id == first_registration.instance_id
        reopened.declare_occurrence(second)
        assert reopened.confirm_static_topology_sync(original).occurrence_count == 2
    finally:
        reopened.close()


def test_static_topology_rejects_curated_operation_without_adapter_target(
    tmp_path: Path,
) -> None:
    runtime = SqliteMessageRuntime.open(
        tmp_path / "runtime.sqlite", runtime_key="test.source-only"
    )
    try:
        runtime.register_source_occurrence(
            instance_key="test.interface.source",
            component_contract_id="component.test.interface",
            binding_id="binding.test.interface.source.v1",
        )
        declaration = ComponentOccurrenceDeclaration(
            instance_key="test.interface.source",
            component_contract_id="component.test.interface",
            binding_id="binding.test.interface.source.v1",
            binding_version=1,
        )
        manifest = RuntimeTopologyManifest(
            runtime_key="test.source-only",
            manifest_schema_version=1,
            occurrences=(declaration,),
            curated_operations=(
                RuntimeCuratedOperationDeclaration(
                    operation_id="source.invalid",
                    target_instance_key="test.interface.source",
                    component_contract_id="component.test.interface",
                    action_id="component.test.interface.invalid",
                    schema_version=1,
                ),
            ),
            manifest_hash="a" * 64,
        )

        with pytest.raises(RuntimeRegistrationInvalid, match="no attached adapter"):
            runtime.confirm_static_topology_sync(manifest)
    finally:
        runtime.close()


def test_runtime_creates_ledger_parent_for_a_fresh_data_root(tmp_path: Path) -> None:
    database = tmp_path / "fresh" / "nested" / "runtime.sqlite"

    runtime = SqliteMessageRuntime.open(database, runtime_key="test.fresh-root")
    try:
        assert database.is_file()
        assert runtime.health == "ready"
    finally:
        runtime.close()


def test_runtime_allocates_and_preserves_first_start_occurrence_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    declaration = ComponentOccurrenceDeclaration(
        instance_key="test.source.primary",
        component_contract_id="component.test.source",
        binding_id="binding.test.source.v1",
        binding_version=1,
        replay_authority=RuntimeReplayMode.EXTERNAL_EXCHANGE,
        configuration_references=("config.source",),
    )
    runtime = SqliteMessageRuntime.open(database, runtime_key="test.identity")
    first = runtime.declare_occurrence(declaration)
    runtime.close()
    restarted = SqliteMessageRuntime.open(database, runtime_key="test.identity")
    try:
        second = restarted.declare_occurrence(declaration)
        assert first.instance_id == second.instance_id
        assert second.configuration_references == ("config.source",)
    finally:
        restarted.close()


def test_terminal_persistence_failure_enters_fail_stop(tmp_path: Path) -> None:
    runtime, counter, client = _runtime_and_counter(tmp_path / "runtime.sqlite")
    try:
        runtime.simulate_ledger_failure_once("response_recorded")
        with pytest.raises(RuntimeFailStopped):
            client.request_sync("component.test.counter.increment", {"amount": 1})
        assert counter.value == 1
        assert runtime.health == "fail_stopped"
        with pytest.raises(RuntimeFailStopped):
            client.request_sync("component.test.counter.increment", {"amount": 1})
    finally:
        runtime.close()


def test_post_effect_terminal_encoding_failure_enters_fail_stop(tmp_path: Path) -> None:
    runtime = SqliteMessageRuntime.open(
        tmp_path / "runtime.sqlite", runtime_key="test.terminal.encoding"
    )
    counter = _Counter()

    def fail_result_encoding(_result: object) -> JsonValue:
        raise ValueError("result encoder exploded")

    descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.invalid_result",
        action_id="component.test.invalid_result.mutate",
        binding_id="binding.test.invalid_result.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.invalid_result.request.json",
        result_codec_id="codec.test.invalid_result.result.json",
        failure_codec_id="codec.test.invalid_result.failure.json",
        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
        replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
    )
    registration = runtime.register_adapter(
        instance_key="test.invalid_result.primary",
        component_contract_id="component.test.invalid_result",
        adapter=ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=descriptor,
                    invoke=counter.increment,
                    decode_request=lambda payload: ((cast(int, payload["amount"]),), {}),
                    encode_result=fail_result_encoding,
                ),
            )
        ),
    )
    address = runtime.address_for(registration.instance_key)
    client = RuntimeClient(
        runtime,
        source=address,
        target=address,
        component_contract_id="component.test.invalid_result",
        request_codec_id="codec.test.invalid_result.request.json",
    )
    envelope = client.envelope("component.test.invalid_result.mutate", {"amount": 2})
    try:
        with pytest.raises(RuntimeFailStopped, match="terminal encoding failed"):
            runtime.request_sync(envelope)
        assert counter.value == 2
        assert runtime.health == "fail_stopped"
        assert runtime.get_trace_sync(envelope.trace_id).disposition is (
            RuntimeTraceDisposition.INDETERMINATE
        )
        with pytest.raises(RuntimeFailStopped):
            client.request_sync("component.test.invalid_result.mutate", {"amount": 1})
        assert counter.value == 2
    finally:
        runtime.close()


def test_fail_stop_quiesces_already_accepted_queued_deliveries(tmp_path: Path) -> None:
    runtime, counter, client = _runtime_and_counter(
        tmp_path / "runtime.sqlite", delay=0.05
    )
    first = client.envelope("component.test.counter.increment", {"amount": 1})
    queued = client.envelope("component.test.counter.increment", {"amount": 10})

    async def request_both() -> tuple[object, object]:
        first_task = asyncio.create_task(runtime.request(first))
        while counter.calls < 1:
            await asyncio.sleep(0.001)
        await runtime.send(queued)
        queued_task = asyncio.create_task(runtime.request(queued))
        first_result, queued_result = await asyncio.gather(
            first_task, queued_task, return_exceptions=True
        )
        return first_result, queued_result

    try:
        runtime.simulate_ledger_failure_once("response_recorded")
        first_result, queued_result = asyncio.run(request_both())

        assert isinstance(first_result, RuntimeFailStopped)
        assert isinstance(queued_result, RuntimeFailStopped)
        assert runtime.health == "fail_stopped"
        assert counter.calls == 1
        assert counter.value == 1
        queued_facts = runtime.query_history_sync(
            RuntimeHistoryQuery(message_id=queued.message_id)
        ).facts
        assert [fact.fact_type for fact in queued_facts] == ["message_accepted"]
    finally:
        runtime.close()


def test_runtime_rejects_noncanonical_json_payloads_before_dispatch(tmp_path: Path) -> None:
    runtime, counter, client = _runtime_and_counter(tmp_path / "runtime.sqlite")
    envelope = client.envelope(
        "component.test.counter.increment",
        cast(JsonObject, {"amount": uuid4()}),
    )
    try:
        with pytest.raises(RuntimeSchemaUnsupported, match="canonical JSON"):
            runtime.request_sync(envelope)
        assert counter.calls == 0
        assert not runtime.query_history_sync(
            RuntimeHistoryQuery(
                message_id=envelope.message_id,
                fact_type="message_accepted",
            )
        ).facts
    finally:
        runtime.close()


def test_runtime_dispatches_the_durable_canonical_payload_copy(tmp_path: Path) -> None:
    runtime, counter, client = _runtime_and_counter(
        tmp_path / "runtime.sqlite", delay=0.05
    )
    first = client.envelope("component.test.counter.increment", {"amount": 1})
    mutable_arguments: JsonObject = {"amount": 2}
    queued = client.envelope("component.test.counter.increment", mutable_arguments)

    async def accept_then_mutate() -> None:
        await runtime.send(first)
        await runtime.send(queued)
        mutable_arguments["amount"] = 99
        while counter.calls < 2:
            await asyncio.sleep(0.01)

    try:
        asyncio.run(accept_then_mutate())
        assert counter.call_order == [1, 2]
        accepted = runtime.query_history_sync(
            RuntimeHistoryQuery(
                message_id=queued.message_id,
                fact_type="message_accepted",
            )
        ).facts
        assert accepted[0].envelope is not None
        assert accepted[0].envelope.payload.value == {"amount": 2}
    finally:
        runtime.close()


def test_timeout_does_not_cancel_or_redeliver(tmp_path: Path) -> None:
    runtime, counter, client = _runtime_and_counter(tmp_path / "runtime.sqlite", delay=0.05)
    try:
        envelope = client.envelope("component.test.counter.increment", {"amount": 3})
        with pytest.raises(RuntimeRequestTimedOut) as captured:
            runtime.request_sync(envelope, timeout_seconds=0.005)
        assert captured.value.message_id == envelope.message_id

        outcome = runtime.request_sync(envelope, timeout_seconds=1)
        assert outcome.response.payload.value == {"result": 3}
        assert counter.calls == 1
    finally:
        runtime.close()


def test_history_is_cursor_paginated_and_filterable(tmp_path: Path) -> None:
    runtime, _, client = _runtime_and_counter(tmp_path / "runtime.sqlite")
    try:
        outcome = client.request_sync("component.test.counter.increment", {"amount": 1})
        first = runtime.query_history_sync(RuntimeHistoryQuery(limit=2))
        assert len(first.facts) == 2
        assert first.next_position == first.facts[-1].runtime_position
        second = runtime.query_history_sync(
            RuntimeHistoryQuery(after_position=first.next_position, limit=100)
        )
        assert second.facts
        assert second.facts[0].runtime_position > first.facts[-1].runtime_position

        filtered = runtime.query_history_sync(
            RuntimeHistoryQuery(
                runtime_id=runtime.runtime_id,
                action_id="component.test.counter.increment",
                message_kind=RuntimeMessageKind.REQUEST,
                schema_version=1,
                delivery_status=RuntimeDeliveryStatus.COMPLETED,
                trace_disposition=RuntimeTraceDisposition.COMMITTED,
                limit=100,
            )
        )
        assert filtered.facts
        assert all(fact.action_id == "component.test.counter.increment" for fact in filtered.facts)
        response_facts = runtime.query_history_sync(
            RuntimeHistoryQuery(correlation_id=outcome.request.message_id)
        ).facts
        assert [fact.fact_type for fact in response_facts] == ["response_recorded"]

        trace = runtime.get_trace_sync(outcome.request.trace_id)
        assert trace.disposition is RuntimeTraceDisposition.COMMITTED
        assert trace.facts[0].fact_type == "message_accepted"
        assert trace.facts[-1].fact_type == "trace_committed"
    finally:
        runtime.close()


def test_same_type_occurrences_are_isolated(tmp_path: Path) -> None:
    runtime = SqliteMessageRuntime.open(tmp_path / "runtime.sqlite", runtime_key="test.runtime")
    try:
        left_graph = InMemoryRtgGraph.empty()
        right_graph = InMemoryRtgGraph.empty()
        left_registration = runtime.register_adapter(
            instance_key="test.graph.left",
            component_contract_id="component.rtg.graph",
            adapter=create_rtg_graph_adapter(left_graph),
        )
        right_registration = runtime.register_adapter(
            instance_key="test.graph.right",
            component_contract_id="component.rtg.graph",
            adapter=create_rtg_graph_adapter(right_graph),
        )
        left = create_rtg_graph_proxy(
            runtime,
            runtime.address_for(right_registration.instance_key),
            runtime.address_for(left_registration.instance_key),
        )
        right = create_rtg_graph_proxy(
            runtime,
            runtime.address_for(left_registration.instance_key),
            runtime.address_for(right_registration.instance_key),
        )

        left_stored = left.put_anchor(RtgAnchor(None, "test.left"))
        right_stored = right.put_anchor(RtgAnchor(None, "test.right"))
        assert left.get_object(left_stored.uuid or UUID(int=0)) == left_stored
        assert right.get_object(right_stored.uuid or UUID(int=0)) == right_stored
        with pytest.raises(RtgGraphObjectNotFound):
            left.get_object(right_stored.uuid or UUID(int=0))
        with pytest.raises(RtgGraphObjectNotFound):
            right.get_object(left_stored.uuid or UUID(int=0))
        assert len(left_graph.export_snapshot().anchors) == 1
        assert len(right_graph.export_snapshot().anchors) == 1
        assert left_registration.instance_id != right_registration.instance_id
    finally:
        runtime.close()


def test_restart_preserves_identity_and_reconstructs_committed_effects(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime, _, client = _runtime_and_counter(database)
    first_registration = runtime.declare_occurrence(
        ComponentOccurrenceDeclaration(
            instance_key="test.counter.primary",
            component_contract_id="component.test.counter",
            binding_id="binding.test.counter.v1",
            binding_version=1,
            replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
        )
    )
    client.request_sync("component.test.counter.increment", {"amount": 4})
    cursor = runtime.current_position
    runtime_id = runtime.runtime_id
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    second_counter = _Counter()
    second_registration = restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(second_counter),
    )
    try:
        report = restarted.reconstruct_sync(RuntimeReconstructionRequest(through_position=cursor))
        assert restarted.runtime_id == runtime_id
        assert second_registration.instance_id == first_registration.instance_id
        assert report.applied_effects == 1
        assert report.verified
        assert len(cast(str, report.state_digests["test.counter.primary"])) == 64
        assert second_counter.value == 4
    finally:
        restarted.close()


def test_async_runtime_api_is_primary(tmp_path: Path) -> None:
    runtime, _, client = _runtime_and_counter(tmp_path / "runtime.sqlite")
    try:
        outcome = asyncio.run(client.request("component.test.counter.increment", {"amount": 1}))
        assert outcome.response.payload.value == {"result": 1}
    finally:
        runtime.close()


def test_address_schema_content_type_and_codec_rejection_have_no_effect(
    tmp_path: Path,
) -> None:
    runtime, counter, client = _runtime_and_counter(tmp_path / "runtime.sqlite")
    try:
        envelope = client.envelope("component.test.counter.increment", {"amount": 1})
        wrong_runtime = replace(
            envelope,
            target=RuntimeAddress(uuid4(), envelope.target.instance_id),
        )
        with pytest.raises(RuntimeAddressUnknown):
            runtime.request_sync(wrong_runtime)
        with pytest.raises(RuntimeAddressUnknown):
            runtime.request_sync(
                replace(
                    envelope,
                    message_id=uuid4(),
                    source=RuntimeAddress(uuid4(), envelope.source.instance_id),
                )
            )
        with pytest.raises(RuntimeAddressUnknown):
            runtime.request_sync(
                replace(
                    envelope,
                    message_id=uuid4(),
                    source=RuntimeAddress(runtime.runtime_id, uuid4()),
                )
            )
        with pytest.raises(RuntimeSchemaUnsupported):
            runtime.request_sync(replace(envelope, message_id=uuid4(), schema_version=2))
        with pytest.raises(RuntimeSchemaUnsupported):
            runtime.request_sync(
                replace(
                    envelope,
                    message_id=uuid4(),
                    payload=replace(envelope.payload, content_type="text/plain"),
                )
            )
        with pytest.raises(RuntimeSchemaUnsupported):
            runtime.request_sync(
                replace(
                    envelope,
                    message_id=uuid4(),
                    payload=replace(envelope.payload, codec_version=2),
                )
            )
        assert counter.calls == 0
        assert (
            len(runtime.query_history_sync(RuntimeHistoryQuery(fact_type="message_rejected")).facts)
            == 6
        )
    finally:
        runtime.close()


def test_serialized_fifo_and_declared_parallel_concurrency(tmp_path: Path) -> None:
    serialized, counter, client = _runtime_and_counter(tmp_path / "serialized.sqlite", delay=0.01)
    try:
        envelopes = tuple(
            client.envelope("component.test.counter.increment", {"amount": amount})
            for amount in (1, 2, 3)
        )

        async def exercise_fifo() -> None:
            for envelope in envelopes:
                await serialized.send(envelope)
            await asyncio.gather(*(serialized.request(envelope) for envelope in envelopes))

        asyncio.run(exercise_fifo())
        assert counter.call_order == [1, 2, 3]
        assert counter.max_active == 1
    finally:
        serialized.close()

    runtime = SqliteMessageRuntime.open(tmp_path / "parallel.sqlite", runtime_key="test.parallel")
    parallel_counter = _Counter(delay=0.05)
    try:
        with pytest.raises(RuntimeRegistrationInvalid, match="concurrency exceeds"):
            runtime.register_adapter(
                instance_key="test.counter.invalid",
                component_contract_id="component.test.counter",
                adapter=_counter_adapter(parallel_counter),
                max_in_flight=2,
            )
        registration = runtime.register_adapter(
            instance_key="test.counter.parallel",
            component_contract_id="component.test.counter",
            adapter=_counter_adapter(parallel_counter, max_in_flight=2),
            max_in_flight=2,
        )
        address = runtime.address_for(registration.instance_key)
        parallel_client = RuntimeClient(
            runtime,
            source=address,
            target=address,
            component_contract_id="component.test.counter",
            request_codec_id="codec.test.counter.request.json",
        )

        async def exercise_parallel() -> None:
            await asyncio.gather(
                parallel_client.request("component.test.counter.increment", {"amount": 1}),
                parallel_client.request("component.test.counter.increment", {"amount": 1}),
            )

        asyncio.run(exercise_parallel())
        assert parallel_counter.max_active == 2
    finally:
        runtime.close()


def test_nested_calls_preserve_causation_and_root_trace_disposition(
    tmp_path: Path,
) -> None:
    runtime = SqliteMessageRuntime.open(tmp_path / "runtime.sqlite", runtime_key="test.nested")
    child_counter = _Counter()
    child_registration = runtime.register_adapter(
        instance_key="test.counter.child",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(child_counter),
    )
    child_address = runtime.address_for(child_registration.instance_key)
    child_client = RuntimeClient(
        runtime,
        source=child_address,
        target=child_address,
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )
    parent_descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.parent",
        action_id="component.test.parent.run",
        binding_id="binding.test.parent.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.parent.request.json",
        result_codec_id="codec.test.parent.result.json",
        failure_codec_id="codec.test.parent.failure.json",
        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
        replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
    )

    def invoke_parent(amount: int) -> int:
        outcome = child_client.request_sync("component.test.counter.increment", {"amount": amount})
        payload = cast(dict[str, object], outcome.response.payload.value)
        return cast(int, payload["result"])

    parent_registration = runtime.register_adapter(
        instance_key="test.parent.primary",
        component_contract_id="component.test.parent",
        adapter=ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=parent_descriptor,
                    invoke=invoke_parent,
                    decode_request=lambda payload: ((cast(int, payload["amount"]),), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    parent_address = runtime.address_for(parent_registration.instance_key)
    parent_client = RuntimeClient(
        runtime,
        source=parent_address,
        target=parent_address,
        component_contract_id="component.test.parent",
        request_codec_id="codec.test.parent.request.json",
    )
    try:
        outcome = parent_client.request_sync("component.test.parent.run", {"amount": 3})
        trace = runtime.get_trace_sync(outcome.request.trace_id)
        accepted = [fact for fact in trace.facts if fact.fact_type == "message_accepted"]
        assert len(accepted) == 2
        root = next(fact for fact in accepted if fact.causation_id is None)
        nested = next(fact for fact in accepted if fact.causation_id is not None)
        assert nested.causation_id == root.message_id
        assert nested.envelope is not None
        assert nested.envelope.payload.value == {"amount": 3}
        assert trace.disposition is RuntimeTraceDisposition.COMMITTED

        runtime.simulate_ledger_failure_once("response_recorded")
        failed_request = parent_client.envelope("component.test.parent.run", {"amount": 1})
        with pytest.raises(RuntimeFailStopped):
            runtime.request_sync(failed_request)
        failed_trace = runtime.get_trace_sync(failed_request.trace_id)
        assert failed_trace.disposition is RuntimeTraceDisposition.INDETERMINATE
        assert runtime.health == "fail_stopped"
        assert not any(fact.fact_type == "trace_committed" for fact in failed_trace.facts)
        assert runtime.health == "fail_stopped"
    finally:
        runtime.close()


def test_root_trace_waits_for_nested_signal_before_committing(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime = SqliteMessageRuntime.open(database, runtime_key="test.signal.trace")
    started = threading.Event()
    release = threading.Event()

    class _BlockingCounter(_Counter):
        def increment(self, amount: int) -> int:
            started.set()
            if not release.wait(timeout=2):
                raise TimeoutError("test did not release nested signal")
            return super().increment(amount)

    child = _BlockingCounter()
    child_registration = runtime.register_adapter(
        instance_key="test.signal.child",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(child),
    )
    parent_registration = runtime.declare_occurrence(
        ComponentOccurrenceDeclaration(
            instance_key="test.signal.parent",
            component_contract_id="component.test.signal_parent",
            binding_id="binding.test.signal_parent.v1",
            binding_version=1,
            replay_authority=RuntimeReplayMode.COORDINATOR_TRACE,
        )
    )
    parent_address = runtime.address_for(parent_registration.instance_key)
    child_client = RuntimeClient(
        runtime,
        source=parent_address,
        target=runtime.address_for(child_registration.instance_key),
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )

    async def coordinate(amount: int) -> str:
        signal = replace(
            child_client.envelope("component.test.counter.increment", {"amount": amount}),
            kind=RuntimeMessageKind.SIGNAL,
        )
        receipt = await runtime.send(signal)
        return str(receipt.message_id)

    runtime.attach_adapter(
        parent_registration,
        ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=RuntimeActionBindingDescriptor(
                        component_contract_id="component.test.signal_parent",
                        action_id="component.test.signal_parent.run",
                        binding_id="binding.test.signal_parent.v1",
                        binding_version=1,
                        schema_version=1,
                        request_codec_id="codec.test.signal_parent.request.json",
                        result_codec_id="codec.test.signal_parent.result.json",
                        failure_codec_id="codec.test.signal_parent.failure.json",
                        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
                        replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
                    ),
                    invoke=coordinate,
                    decode_request=lambda payload: ((cast(int, payload["amount"]),), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    parent_client = RuntimeClient(
        runtime,
        source=parent_address,
        target=parent_address,
        component_contract_id="component.test.signal_parent",
        request_codec_id="codec.test.signal_parent.request.json",
    )
    outcomes: list[RuntimeRequestOutcome] = []
    failures: list[BaseException] = []

    def invoke_root() -> None:
        try:
            outcomes.append(
                parent_client.request_sync("component.test.signal_parent.run", {"amount": 3})
            )
        except BaseException as error:  # pragma: no cover - diagnostic collection
            failures.append(error)

    caller = threading.Thread(target=invoke_root)
    caller.start()
    try:
        assert started.wait(timeout=2)
        assert caller.is_alive()
        assert not outcomes
        release.set()
        caller.join(timeout=2)
        assert not caller.is_alive()
        assert not failures
        outcome = outcomes[0]
        trace_id = outcome.request.trace_id
        trace = runtime.get_trace_sync(trace_id)
        fact_types = [fact.fact_type for fact in trace.facts]
        assert fact_types[-1] == "trace_committed"
        assert fact_types.index("delivery_completed") < fact_types.index("trace_committed")
        assert child.value == 3
        cursor = runtime.current_position
    finally:
        release.set()
        caller.join(timeout=2)
        runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.signal.trace")
    restored = _Counter()
    restarted.register_adapter(
        instance_key="test.signal.child",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(restored),
    )
    try:
        report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(through_position=cursor)
        )
        assert report.verified
        assert report.applied_effects == 1
        assert restored.value == 3
    finally:
        restarted.close()


def test_nested_signal_uncertainty_marks_trace_and_runtime_recovery_required(
    tmp_path: Path,
) -> None:
    runtime = SqliteMessageRuntime.open(
        tmp_path / "runtime.sqlite", runtime_key="test.signal.indeterminate"
    )
    calls = 0

    def uncertain_child() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("uncertain signal failure")

    child_registration = runtime.register_adapter(
        instance_key="test.signal.uncertain_child",
        component_contract_id="component.test.signal_child",
        adapter=ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=RuntimeActionBindingDescriptor(
                        component_contract_id="component.test.signal_child",
                        action_id="component.test.signal_child.run",
                        binding_id="binding.test.signal_child.v1",
                        binding_version=1,
                        schema_version=1,
                        request_codec_id="codec.test.signal_child.request.json",
                        result_codec_id="codec.test.signal_child.result.json",
                        failure_codec_id="codec.test.signal_child.failure.json",
                        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
                        replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
                    ),
                    invoke=uncertain_child,
                    decode_request=lambda _payload: ((), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    parent_registration = runtime.declare_occurrence(
        ComponentOccurrenceDeclaration(
            instance_key="test.signal.uncertain_parent",
            component_contract_id="component.test.signal_parent",
            binding_id="binding.test.signal_parent.v1",
            binding_version=1,
            replay_authority=RuntimeReplayMode.COORDINATOR_TRACE,
        )
    )
    parent_address = runtime.address_for(parent_registration.instance_key)
    child_address = runtime.address_for(child_registration.instance_key)

    async def coordinate() -> str:
        current = runtime.current_envelope()
        assert current is not None
        signal = RuntimeClient(
            runtime,
            source=parent_address,
            target=child_address,
            component_contract_id="component.test.signal_child",
            request_codec_id="codec.test.signal_child.request.json",
        ).envelope("component.test.signal_child.run", {})
        receipt = await runtime.send(replace(signal, kind=RuntimeMessageKind.SIGNAL))
        return str(receipt.message_id)

    parent_descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.signal_parent",
        action_id="component.test.signal_parent.run",
        binding_id="binding.test.signal_parent.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.signal_parent.request.json",
        result_codec_id="codec.test.signal_parent.result.json",
        failure_codec_id="codec.test.signal_parent.failure.json",
        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
        replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
    )
    runtime.attach_adapter(
        parent_registration,
        ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=parent_descriptor,
                    invoke=coordinate,
                    decode_request=lambda _payload: ((), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    client = RuntimeClient(
        runtime,
        source=parent_address,
        target=parent_address,
        component_contract_id="component.test.signal_parent",
        request_codec_id="codec.test.signal_parent.request.json",
    )
    try:
        envelope = client.envelope("component.test.signal_parent.run", {})
        outcome = runtime.request_sync(envelope)
        assert outcome.trace_disposition is RuntimeTraceDisposition.INDETERMINATE
        assert runtime.get_trace_sync(outcome.request.trace_id).disposition is (
            RuntimeTraceDisposition.INDETERMINATE
        )
        assert runtime.health == "recovery_required"
        assert calls == 1
        duplicate = runtime.request_sync(envelope)
        assert duplicate.terminal_position == outcome.terminal_position
        assert duplicate.response == outcome.response
        assert calls == 1
        with pytest.raises(RuntimeFailStopped, match="recovery_required"):
            client.request_sync("component.test.signal_parent.run", {})
    finally:
        runtime.close()


def test_post_terminal_causal_signal_is_rejected_without_poisoning_replay(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime, counter, counter_client = _runtime_and_counter(database)
    parent_registration = runtime.declare_occurrence(
        ComponentOccurrenceDeclaration(
            instance_key="test.late_signal.parent",
            component_contract_id="component.test.late_signal_parent",
            binding_id="binding.test.late_signal_parent.v1",
            binding_version=1,
            replay_authority=RuntimeReplayMode.COORDINATOR_TRACE,
        )
    )
    parent_address = runtime.address_for(parent_registration.instance_key)
    delayed_done = threading.Event()
    delayed_errors: list[Exception] = []
    child = RuntimeClient(
        runtime,
        source=parent_address,
        target=runtime.address_for("test.counter.primary"),
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )

    async def coordinate() -> str:
        async def delayed_send() -> None:
            await asyncio.sleep(0.05)
            try:
                signal = replace(
                    child.envelope("component.test.counter.increment", {"amount": 7}),
                    kind=RuntimeMessageKind.SIGNAL,
                )
                await runtime.send(signal)
            except Exception as error:  # expected rejection is asserted below
                delayed_errors.append(error)
            finally:
                delayed_done.set()

        asyncio.create_task(delayed_send())
        return "scheduled"

    runtime.attach_adapter(
        parent_registration,
        ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=RuntimeActionBindingDescriptor(
                        component_contract_id="component.test.late_signal_parent",
                        action_id="component.test.late_signal_parent.run",
                        binding_id="binding.test.late_signal_parent.v1",
                        binding_version=1,
                        schema_version=1,
                        request_codec_id="codec.test.late_signal_parent.request.json",
                        result_codec_id="codec.test.late_signal_parent.result.json",
                        failure_codec_id="codec.test.late_signal_parent.failure.json",
                        idempotency=RuntimeActionIdempotency.IDEMPOTENT,
                        replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
                    ),
                    invoke=coordinate,
                    decode_request=lambda _payload: ((), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    parent_client = RuntimeClient(
        runtime,
        source=parent_address,
        target=parent_address,
        component_contract_id="component.test.late_signal_parent",
        request_codec_id="codec.test.late_signal_parent.request.json",
    )
    try:
        outcome = parent_client.request_sync("component.test.late_signal_parent.run", {})
        assert outcome.trace_disposition is RuntimeTraceDisposition.COMMITTED
        assert delayed_done.wait(timeout=2)
        assert len(delayed_errors) == 1
        assert isinstance(delayed_errors[0], RuntimeRegistrationInvalid)
        assert counter.calls == 0
        trace = runtime.get_trace_sync(outcome.request.trace_id)
        assert trace.disposition is RuntimeTraceDisposition.COMMITTED
        assert not any(fact.fact_type == "delivery_completed" for fact in trace.facts)
        cursor = runtime.current_position
    finally:
        runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    restored = _Counter()
    restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(restored),
    )
    try:
        report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(through_position=cursor)
        )
        assert report.verified
        assert report.applied_effects == 0
        assert restored.value == 0
    finally:
        restarted.close()


def test_root_trace_disposition_selects_effects_for_historical_replay(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime = SqliteMessageRuntime.open(database, runtime_key="test.replay.dispositions")
    counter = _Counter()
    counter_registration = runtime.register_adapter(
        instance_key="test.counter.state",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(counter),
    )
    counter_address = runtime.address_for(counter_registration.instance_key)
    counter_client = RuntimeClient(
        runtime,
        source=counter_address,
        target=counter_address,
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )

    def expected_failure() -> None:
        raise _ExpectedFailure("modeled rejection")

    def unexpected_failure() -> None:
        raise RuntimeError("unconfirmed failure")

    guard_bindings: list[ActionBinding] = []
    for suffix, invoke, failure_types in (
        ("abort", expected_failure, (_ExpectedFailure,)),
        ("indeterminate", unexpected_failure, ()),
    ):
        guard_bindings.append(
            ActionBinding(
                descriptor=RuntimeActionBindingDescriptor(
                    component_contract_id="component.test.guard",
                    action_id=f"component.test.guard.{suffix}",
                    binding_id="binding.test.guard.v1",
                    binding_version=1,
                    schema_version=1,
                    request_codec_id="codec.test.guard.request.json",
                    result_codec_id="codec.test.guard.result.json",
                    failure_codec_id="codec.test.guard.failure.json",
                    idempotency=RuntimeActionIdempotency.IDEMPOTENT,
                    replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
                ),
                invoke=invoke,
                decode_request=lambda _payload: ((), {}),
                encode_result=encode_json,
                failure_types=failure_types,
            )
        )
    guard_registration = runtime.register_adapter(
        instance_key="test.guard.primary",
        component_contract_id="component.test.guard",
        adapter=ExplicitComponentAdapter(tuple(guard_bindings)),
    )
    guard_address = runtime.address_for(guard_registration.instance_key)
    guard_client = RuntimeClient(
        runtime,
        source=guard_address,
        target=guard_address,
        component_contract_id="component.test.guard",
        request_codec_id="codec.test.guard.request.json",
    )

    def coordinate_handled_fault() -> int:
        counter_client.request_sync("component.test.counter.increment", {"amount": 1})
        # A coordinator may intentionally handle an expected collaborator miss.
        guard_client.request_sync("component.test.guard.abort", {})
        return counter.value

    def coordinate_aborted() -> int:
        counter_client.request_sync("component.test.counter.increment", {"amount": 1})
        counter_client.request_sync("component.test.counter.increment", {"amount": -1})
        raise _ExpectedFailure("root modeled rejection")

    def coordinate_indeterminate() -> int:
        counter_client.request_sync("component.test.counter.increment", {"amount": 1})
        # A caught unmodeled collaborator failure still makes the trace uncertain.
        guard_client.request_sync("component.test.guard.indeterminate", {})
        return counter.value

    parent_bindings = tuple(
        ActionBinding(
            descriptor=RuntimeActionBindingDescriptor(
                component_contract_id="component.test.coordinator",
                action_id=f"component.test.coordinator.{suffix}",
                binding_id="binding.test.coordinator.v1",
                binding_version=1,
                schema_version=1,
                request_codec_id="codec.test.coordinator.request.json",
                result_codec_id="codec.test.coordinator.result.json",
                failure_codec_id="codec.test.coordinator.failure.json",
                idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
                replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
            ),
            invoke=invoke,
            decode_request=lambda _payload: ((), {}),
            encode_result=encode_json,
            failure_types=failure_types,
        )
        for suffix, invoke, failure_types in (
            ("handled", coordinate_handled_fault, ()),
            ("aborted", coordinate_aborted, (_ExpectedFailure,)),
            ("indeterminate", coordinate_indeterminate, ()),
        )
    )
    parent_registration = runtime.register_adapter(
        instance_key="test.coordinator.primary",
        component_contract_id="component.test.coordinator",
        adapter=ExplicitComponentAdapter(parent_bindings),
    )
    parent_address = runtime.address_for(parent_registration.instance_key)
    parent_client = RuntimeClient(
        runtime,
        source=parent_address,
        target=parent_address,
        component_contract_id="component.test.coordinator",
        request_codec_id="codec.test.coordinator.request.json",
    )
    handled = parent_client.request_sync("component.test.coordinator.handled", {})
    handled_cursor = runtime.current_position
    aborted = parent_client.request_sync("component.test.coordinator.aborted", {})
    aborted_cursor = runtime.current_position
    counter_client.request_sync("component.test.counter.increment", {"amount": 5})
    final_cursor = runtime.current_position
    indeterminate = parent_client.request_sync("component.test.coordinator.indeterminate", {})
    indeterminate_cursor = runtime.current_position
    assert runtime.health == "recovery_required"
    assert runtime.get_trace_sync(handled.request.trace_id).disposition is (
        RuntimeTraceDisposition.COMMITTED
    )
    assert runtime.get_trace_sync(aborted.request.trace_id).disposition is (
        RuntimeTraceDisposition.ABORTED
    )
    assert runtime.get_trace_sync(indeterminate.request.trace_id).disposition is (
        RuntimeTraceDisposition.INDETERMINATE
    )
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.replay.dispositions")
    restored_counter = _Counter()
    restarted.register_adapter(
        instance_key="test.counter.state",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(restored_counter),
    )
    try:
        handled_report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(through_position=handled_cursor)
        )
        assert handled_report.applied_effects == 1
        assert restored_counter.value == 1
        assert restarted.health == "branch_pending"
        assert handled_report.verified_digest is not None
        restarted.record_branch_provenance_sync(
            source_runtime_id=restarted.runtime_id,
            source_cursor=handled_cursor,
            verified_digest=handled_report.verified_digest,
        )

        aborted_report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(
                through_position=aborted_cursor,
                reset_targets=True,
            )
        )
        assert aborted_report.verified_digest is not None
        restarted.record_branch_provenance_sync(
            source_runtime_id=restarted.runtime_id,
            source_cursor=aborted_cursor,
            verified_digest=aborted_report.verified_digest,
        )
        committed_report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(
                through_position=final_cursor,
                reset_targets=True,
            )
        )
        assert aborted_report.applied_effects == 1
        assert committed_report.applied_effects == 2
        assert restored_counter.value == 6
        assert committed_report.verified_digest is not None
        restarted.record_branch_provenance_sync(
            source_runtime_id=restarted.runtime_id,
            source_cursor=final_cursor,
            verified_digest=committed_report.verified_digest,
        )

        indeterminate_report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(
                through_position=indeterminate_cursor,
                reset_targets=True,
            )
        )
        assert indeterminate_report.applied_effects == 2
        assert restored_counter.value == 6
    finally:
        restarted.close()


def test_final_aggregate_effect_supersedes_derived_effects_in_its_trace(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"

    def attach_aggregate(
        runtime: SqliteMessageRuntime,
        counter: _Counter,
    ) -> RuntimeClient:
        registration = runtime.declare_occurrence(
            ComponentOccurrenceDeclaration(
                instance_key="test.aggregate.primary",
                component_contract_id="component.test.aggregate",
                binding_id="binding.test.aggregate.v1",
                binding_version=1,
                replay_authority=RuntimeReplayMode.COORDINATOR_TRACE,
            )
        )
        address = runtime.address_for(registration.instance_key)
        child = RuntimeClient(
            runtime,
            source=address,
            target=runtime.address_for("test.counter.primary"),
            component_contract_id="component.test.counter",
            request_codec_id="codec.test.counter.request.json",
        )

        def compensate_then_fail(amount: int) -> None:
            child.request_sync("component.test.counter.increment", {"amount": amount})
            child.request_sync("component.test.counter.increment", {"amount": -amount})
            raise _ExpectedFailure("aggregate workflow restored its final state")

        descriptor = RuntimeActionBindingDescriptor(
            component_contract_id="component.test.aggregate",
            action_id="component.test.aggregate.run",
            binding_id="binding.test.aggregate.v1",
            binding_version=1,
            schema_version=1,
            request_codec_id="codec.test.aggregate.request.json",
            result_codec_id="codec.test.aggregate.result.json",
            failure_codec_id="codec.test.aggregate.failure.json",
            idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
            replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
            modeled_fault_trace_disposition=RuntimeTraceDisposition.COMMITTED,
        )
        runtime.attach_adapter(
            registration,
            ExplicitComponentAdapter(
                (
                    ActionBinding(
                        descriptor=descriptor,
                        invoke=compensate_then_fail,
                        decode_request=lambda payload: (
                            (cast(int, payload["amount"]),),
                            {},
                        ),
                        encode_result=encode_json,
                        failure_types=(_ExpectedFailure,),
                        build_failure_replay_effect=lambda _error: {
                            "supersedes_trace_effects": True,
                            "final_value": counter.value,
                        },
                        apply_replay_effect=lambda payload: setattr(
                            counter, "value", cast(int, payload["final_value"])
                        ),
                    ),
                )
            ),
        )
        return RuntimeClient(
            runtime,
            source=address,
            target=address,
            component_contract_id="component.test.aggregate",
            request_codec_id="codec.test.aggregate.request.json",
        )

    runtime, counter, counter_client = _runtime_and_counter(database)
    counter_client.request_sync("component.test.counter.increment", {"amount": 10})
    aggregate_client = attach_aggregate(runtime, counter)
    failed = aggregate_client.request_sync("component.test.aggregate.run", {"amount": 3})
    cursor = runtime.current_position
    assert failed.response.kind is RuntimeMessageKind.FAULT
    assert failed.trace_disposition is RuntimeTraceDisposition.COMMITTED
    assert counter.value == 10
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    restored = _Counter()
    restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(restored),
    )
    attach_aggregate(restarted, restored)
    try:
        report = restarted.reconstruct_sync(RuntimeReconstructionRequest(through_position=cursor))
        assert report.verified
        assert report.applied_effects == 2
        assert report.skipped_effects == 2
        assert restored.value == 10
    finally:
        restarted.close()


def test_historical_reconstruction_requires_durable_branch_provenance_before_ingress(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime, counter, client = _runtime_and_counter(database)
    runtime_id = runtime.runtime_id
    client.request_sync("component.test.counter.increment", {"amount": 1})
    branch_cursor = runtime.current_position
    with pytest.raises(RuntimeActionUnknown):
        client.request_sync("component.test.counter.missing", {})
    assert runtime.query_history_sync(
        RuntimeHistoryQuery(
            after_position=branch_cursor,
            fact_type="canonical_effect",
        )
    ).facts == ()

    report = runtime.reconstruct_sync(
        RuntimeReconstructionRequest(
            through_position=branch_cursor,
            reset_targets=True,
        )
    )
    assert report.verified
    assert report.verified_digest is not None
    assert counter.value == 1
    assert runtime.health == "branch_pending"
    with pytest.raises(RuntimeFailStopped, match="branch_pending"):
        client.request_sync("component.test.counter.increment", {"amount": 1})
    with pytest.raises(RuntimeReplayIncompatible, match="does not match"):
        runtime.record_branch_provenance_sync(
            source_runtime_id=runtime_id,
            source_cursor=branch_cursor,
            verified_digest="0" * 64,
        )
    required = runtime.query_history_sync(
        RuntimeHistoryQuery(fact_type="branch_provenance_required")
    ).facts
    assert len(required) == 1
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    restored = _Counter()
    restored.value = 1
    registration = restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(restored),
    )
    address = restarted.address_for(registration.instance_key)
    restarted_client = RuntimeClient(
        restarted,
        source=address,
        target=address,
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )
    try:
        assert restarted.health == "branch_pending"
        with pytest.raises(RuntimeFailStopped, match="branch_pending"):
            restarted_client.request_sync(
                "component.test.counter.increment", {"amount": 1}
            )
        position = asyncio.run(
            restarted.record_branch_provenance(
                source_runtime_id=runtime_id,
                source_cursor=branch_cursor,
                verified_digest=report.verified_digest,
            )
        )
        assert restarted.health == "ready"
        provenance = restarted.query_history_sync(
            RuntimeHistoryQuery(
                after_position=position - 1,
                fact_type="branch_provenance",
            )
        ).facts
        assert len(provenance) == 1
        restarted_client.request_sync(
            "component.test.counter.increment", {"amount": 2}
        )
        assert restored.value == 3
    finally:
        restarted.close()


def test_reconstruction_requires_empty_reset_checkpoint_or_confirmed_state(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime, _, client = _runtime_and_counter(database)
    client.request_sync("component.test.counter.increment", {"amount": 4})
    cursor = runtime.current_position
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    target = _Counter()
    target.value = 99
    restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(target),
    )
    try:
        with pytest.raises(RuntimeReplayTargetNotPrepared, match="not empty or confirmed"):
            restarted.reconstruct_sync(RuntimeReconstructionRequest(through_position=cursor))
        rejected = restarted.query_history_sync(
            RuntimeHistoryQuery(fact_type="reconstruction_rejected")
        )
        assert len(rejected.facts) == 1

        checkpoint = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(
                through_position=cursor,
                checkpoint_reference=f"{cursor}:4",
                reset_targets=True,
            )
        )
        assert checkpoint.applied_effects == 0
        assert checkpoint.skipped_effects == 1
        assert checkpoint.verified
        assert target.value == 4

        rebuilt = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(
                through_position=cursor,
                reset_targets=True,
            )
        )
        assert rebuilt.applied_effects == 1
        assert rebuilt.verified
        assert target.value == 4
        assert len(cast(str, rebuilt.state_digests["test.counter.primary"])) == 64
    finally:
        restarted.close()

    durable = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    durable_target = _Counter()
    durable_target.value = 4
    durable.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(durable_target, confirmed_cursor=cursor),
    )
    try:
        report = durable.reconstruct_sync(RuntimeReconstructionRequest(through_position=cursor))
        assert report.applied_effects == 0
        assert report.skipped_effects == 1
        assert report.verified
        assert durable_target.value == 4
    finally:
        durable.close()


def test_root_coordinator_may_initiate_reconstruction_as_only_pending_delivery(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"

    def attach_coordinator(runtime: SqliteMessageRuntime) -> RuntimeClient:
        descriptor = RuntimeActionBindingDescriptor(
            component_contract_id="component.test.recovery_coordinator",
            action_id="component.test.recovery_coordinator.reconstruct",
            binding_id="binding.test.recovery_coordinator.v1",
            binding_version=1,
            schema_version=1,
            request_codec_id="codec.test.recovery_coordinator.request.json",
            result_codec_id="codec.test.recovery_coordinator.result.json",
            failure_codec_id="codec.test.recovery_coordinator.failure.json",
            idempotency=RuntimeActionIdempotency.IDEMPOTENT,
            replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
            recovery_authorized=True,
        )

        def reconstruct() -> object:
            return runtime.reconstruct_sync(RuntimeReconstructionRequest())

        registration = runtime.register_adapter(
            instance_key="test.recovery_coordinator.primary",
            component_contract_id="component.test.recovery_coordinator",
            adapter=ExplicitComponentAdapter(
                (
                    ActionBinding(
                        descriptor=descriptor,
                        invoke=reconstruct,
                        decode_request=lambda _payload: ((), {}),
                        encode_result=encode_json,
                    ),
                )
            ),
        )
        address = runtime.address_for(registration.instance_key)
        return RuntimeClient(
            runtime,
            source=address,
            target=address,
            component_contract_id="component.test.recovery_coordinator",
            request_codec_id="codec.test.recovery_coordinator.request.json",
        )

    initial, _counter, counter_client = _runtime_and_counter(database)
    attach_coordinator(initial)
    counter_client.request_sync("component.test.counter.increment", {"amount": 4})
    initial.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    restored = _Counter()
    restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(restored),
    )
    coordinator = attach_coordinator(restarted)
    effects_before = restarted.query_history_sync(
        RuntimeHistoryQuery(fact_type="canonical_effect", limit=1000)
    ).facts
    messages_before = restarted.query_history_sync(
        RuntimeHistoryQuery(fact_type="message_accepted", limit=1000)
    ).facts
    try:
        outcome = coordinator.request_sync(
            "component.test.recovery_coordinator.reconstruct", {}
        )
        payload = cast(dict[str, object], outcome.response.payload.value)
        report = cast(dict[str, object], payload["result"])
        effects_after = restarted.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect", limit=1000)
        ).facts
        messages_after = restarted.query_history_sync(
            RuntimeHistoryQuery(fact_type="message_accepted", limit=1000)
        ).facts
        assert report["verified"] is True
        assert report["applied_effects"] == 1
        assert restored.value == 4
        assert effects_after == effects_before
        assert len(messages_after) == len(messages_before) + 1
    finally:
        restarted.close()


def test_checkpoint_digest_is_verified_before_later_effects(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime, _, client = _runtime_and_counter(database)
    client.request_sync("component.test.counter.increment", {"amount": 4})
    cursor = runtime.current_position
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    target = _Counter()
    restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(target, invalid_checkpoint_digest=True),
    )
    try:
        with pytest.raises(RuntimeReplayTargetNotPrepared, match="checkpoint digest differs"):
            restarted.reconstruct_sync(
                RuntimeReconstructionRequest(
                    through_position=cursor,
                    checkpoint_reference="0:2",
                    reset_targets=True,
                )
            )
        assert target.value == 2
        assert target.calls == 0
        assert restarted.health == "recovery_required"
    finally:
        restarted.close()


def test_recovery_ingress_reserves_one_root_until_its_trace_finishes(
    tmp_path: Path,
) -> None:
    runtime = SqliteMessageRuntime.open(
        tmp_path / "runtime.sqlite", runtime_key="test.recovery.reservation"
    )
    started = threading.Event()
    release = threading.Event()

    def uncertain() -> None:
        raise RuntimeError("unconfirmed effect")

    uncertain_descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.uncertain",
        action_id="component.test.uncertain.run",
        binding_id="binding.test.uncertain.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.uncertain.request.json",
        result_codec_id="codec.test.uncertain.result.json",
        failure_codec_id="codec.test.uncertain.failure.json",
        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
        replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
    )
    uncertain_registration = runtime.register_adapter(
        instance_key="test.uncertain.primary",
        component_contract_id="component.test.uncertain",
        adapter=ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=uncertain_descriptor,
                    invoke=uncertain,
                    decode_request=lambda _payload: ((), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    uncertain_address = runtime.address_for(uncertain_registration.instance_key)
    uncertain_client = RuntimeClient(
        runtime,
        source=uncertain_address,
        target=uncertain_address,
        component_contract_id="component.test.uncertain",
        request_codec_id="codec.test.uncertain.request.json",
    )

    def recover() -> object:
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError("test did not release recovery coordinator")
        return runtime.reconstruct_sync(RuntimeReconstructionRequest())

    recovery_descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.recovery",
        action_id="component.test.recovery.run",
        binding_id="binding.test.recovery.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.recovery.request.json",
        result_codec_id="codec.test.recovery.result.json",
        failure_codec_id="codec.test.recovery.failure.json",
        idempotency=RuntimeActionIdempotency.IDEMPOTENT,
        replay_mode=RuntimeReplayMode.COORDINATOR_TRACE,
        recovery_authorized=True,
    )
    recovery_registration = runtime.register_adapter(
        instance_key="test.recovery.primary",
        component_contract_id="component.test.recovery",
        adapter=ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=recovery_descriptor,
                    invoke=recover,
                    decode_request=lambda _payload: ((), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    recovery_address = runtime.address_for(recovery_registration.instance_key)
    recovery_client = RuntimeClient(
        runtime,
        source=recovery_address,
        target=recovery_address,
        component_contract_id="component.test.recovery",
        request_codec_id="codec.test.recovery.request.json",
    )

    first_outcomes: list[RuntimeRequestOutcome] = []
    first_failures: list[BaseException] = []

    def request_recovery() -> None:
        try:
            first_outcomes.append(
                recovery_client.request_sync("component.test.recovery.run", {})
            )
        except BaseException as error:
            first_failures.append(error)

    first_caller = threading.Thread(target=request_recovery)
    try:
        uncertain_outcome = uncertain_client.request_sync(
            "component.test.uncertain.run", {}
        )
        assert uncertain_outcome.trace_disposition is RuntimeTraceDisposition.INDETERMINATE
        assert runtime.health == "recovery_required"

        first_caller.start()
        assert started.wait(timeout=2)
        with pytest.raises(RuntimeFailStopped, match="recovery ingress"):
            recovery_client.request_sync("component.test.recovery.run", {})
        release.set()
        first_caller.join(timeout=3)
        assert not first_caller.is_alive()
        assert first_failures == []
        assert len(first_outcomes) == 1
        assert first_outcomes[0].trace_disposition is RuntimeTraceDisposition.COMMITTED
        assert runtime.health == "ready"
    finally:
        release.set()
        first_caller.join(timeout=3)
        runtime.close()


def test_reconstruction_rejects_a_canonical_effect_with_a_changed_digest(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime, _, client = _runtime_and_counter(database)
    try:
        client.request_sync("component.test.counter.increment", {"amount": 2})
    finally:
        runtime.close()

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT runtime_position, details_json FROM runtime_ledger "
            "WHERE fact_type = 'canonical_effect'"
        ).fetchone()
        assert row is not None
        details = json.loads(cast(str, row[1]))
        details["effect"]["payload"]["amount"] = 99
        connection.execute(
            "UPDATE runtime_ledger SET details_json = ? WHERE runtime_position = ?",
            (json.dumps(details, sort_keys=True, separators=(",", ":")), int(row[0])),
        )

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    target = _Counter()
    restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(target),
    )
    try:
        report = restarted.reconstruct_sync(RuntimeReconstructionRequest())
        assert not report.verified
        assert report.applied_effects == 0
        assert report.incompatible_effects == 1
        assert "digest mismatch" in " ".join(report.limitations)
        assert target.calls == 0
        assert target.value == 0
        assert restarted.health == "recovery_required"
    finally:
        restarted.close()


def test_external_exchange_is_playback_only(
    tmp_path: Path,
) -> None:
    runtime = SqliteMessageRuntime.open(tmp_path / "runtime.sqlite", runtime_key="test.external")
    calls = 0

    def exchange(value: str) -> str:
        nonlocal calls
        calls += 1
        return value.upper()

    descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.external",
        action_id="component.test.external.exchange",
        binding_id="binding.test.external.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.external.request.json",
        result_codec_id="codec.test.external.result.json",
        failure_codec_id="codec.test.external.failure.json",
        idempotency=RuntimeActionIdempotency.UNSPECIFIED,
        replay_mode=RuntimeReplayMode.EXTERNAL_EXCHANGE,
        externally_effectful=True,
    )
    registration = runtime.register_adapter(
        instance_key="test.external.primary",
        component_contract_id="component.test.external",
        adapter=ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=descriptor,
                    invoke=exchange,
                    decode_request=lambda payload: ((cast(str, payload["value"]),), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    address = runtime.address_for(registration.instance_key)
    client = RuntimeClient(
        runtime,
        source=address,
        target=address,
        component_contract_id="component.test.external",
        request_codec_id="codec.test.external.request.json",
    )
    try:
        outcome = client.request_sync("component.test.external.exchange", {"value": "hello"})
        cursor = runtime.current_position
        assert calls == 1
        report = runtime.reconstruct_sync(RuntimeReconstructionRequest(through_position=cursor))
        assert report.start_position == 0
        assert report.external_effects_skipped == 1
        assert report.external_boundaries == (
            RuntimeExternalBoundaryDisposition(
                boundary_id="test.external.primary",
                mode=RuntimeExternalBoundaryMode.PLAYBACK_ONLY,
            ),
        )
        assert report.verified
        assert calls == 1
        with pytest.raises(RuntimeReplayIncompatible, match="historical reconstruction"):
            runtime.record_branch_provenance_sync(
                source_runtime_id=runtime.runtime_id,
                source_cursor=cursor,
                verified_digest="b" * 64,
            )
        assert outcome.trace_disposition is RuntimeTraceDisposition.COMMITTED
    finally:
        runtime.close()


def test_recorded_external_response_is_supplied_without_a_live_collaborator(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    external_descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.external",
        action_id="component.test.external.exchange",
        binding_id="binding.test.external.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.external.request.json",
        result_codec_id="codec.test.external.result.json",
        failure_codec_id="codec.test.external.failure.json",
        idempotency=RuntimeActionIdempotency.UNSPECIFIED,
        replay_mode=RuntimeReplayMode.EXTERNAL_EXCHANGE,
        externally_effectful=True,
    )
    parent_descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.test.external_parent",
        action_id="component.test.external_parent.resolve",
        binding_id="binding.test.external_parent.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.test.external_parent.request.json",
        result_codec_id="codec.test.external_parent.result.json",
        failure_codec_id="codec.test.external_parent.failure.json",
        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
        replay_mode=RuntimeReplayMode.CANONICAL_EFFECT,
    )

    def attach_parent(
        runtime: SqliteMessageRuntime,
        state: dict[str, str | None],
    ) -> tuple[RuntimeClient, RuntimeAddress]:
        registration = runtime.declare_occurrence(
            ComponentOccurrenceDeclaration(
                instance_key="test.external_parent.primary",
                component_contract_id="component.test.external_parent",
                binding_id="binding.test.external_parent.v1",
                binding_version=1,
                replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
            )
        )
        parent_address = runtime.address_for(registration.instance_key)
        external_address = runtime.address_for("test.external.primary")
        external_client = RuntimeClient(
            runtime,
            source=parent_address,
            target=external_address,
            component_contract_id="component.test.external",
            request_codec_id="codec.test.external.request.json",
        )

        def resolve(value: str) -> str:
            outcome = external_client.request_sync(
                "component.test.external.exchange", {"value": value}
            )
            payload = outcome.response.payload.value
            if not isinstance(payload, dict) or not isinstance(payload.get("result"), str):
                raise AssertionError("recorded external result is not a string")
            resolved = cast(str, payload["result"])
            state["value"] = resolved
            return resolved

        runtime.attach_adapter(
            registration,
            ExplicitComponentAdapter(
                (
                    ActionBinding(
                        descriptor=parent_descriptor,
                        invoke=resolve,
                        decode_request=lambda payload: ((cast(str, payload["value"]),), {}),
                        encode_result=encode_json,
                        build_replay_effect=lambda args, _kwargs, _result: {
                            "value": cast(str, args[0])
                        },
                        apply_replay_effect=lambda payload: resolve(
                            cast(str, payload["value"])
                        ),
                    ),
                ),
                replay_state=ReplayStateBinding(
                    is_empty=lambda: state["value"] is None,
                    reset=lambda: state.update(value=None),
                    import_checkpoint=lambda _reference: 0,
                    export_state=lambda: dict(state),
                ),
            ),
        )
        return (
            RuntimeClient(
                runtime,
                source=parent_address,
                target=parent_address,
                component_contract_id="component.test.external_parent",
                request_codec_id="codec.test.external_parent.request.json",
            ),
            parent_address,
        )

    runtime = SqliteMessageRuntime.open(database, runtime_key="test.external.playback")
    external_calls = 0

    def exchange(value: str) -> str:
        nonlocal external_calls
        external_calls += 1
        return value.upper()

    runtime.register_adapter(
        instance_key="test.external.primary",
        component_contract_id="component.test.external",
        adapter=ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=external_descriptor,
                    invoke=exchange,
                    decode_request=lambda payload: ((cast(str, payload["value"]),), {}),
                    encode_result=encode_json,
                ),
            )
        ),
    )
    source_state: dict[str, str | None] = {"value": None}
    source_client, _ = attach_parent(runtime, source_state)
    outcome = source_client.request_sync(
        "component.test.external_parent.resolve", {"value": "hello"}
    )
    cursor = runtime.current_position
    assert outcome.response.payload.value == {"result": "HELLO"}
    assert source_state == {"value": "HELLO"}
    assert external_calls == 1
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.external.playback")
    restored_state: dict[str, str | None] = {"value": None}
    attach_parent(restarted, restored_state)
    try:
        with pytest.raises(RuntimeReplayIncompatible, match="unknown occurrences"):
            restarted.reconstruct_sync(
                RuntimeReconstructionRequest(
                    through_position=cursor,
                    external_boundaries=(
                        RuntimeExternalBoundaryDisposition(
                            boundary_id="test.external.unknown",
                            mode=RuntimeExternalBoundaryMode.LIVE,
                        ),
                    ),
                )
            )
        assert restored_state == {"value": None}

        boundary = RuntimeExternalBoundaryDisposition(
            boundary_id="test.external.primary",
            mode=RuntimeExternalBoundaryMode.UNAVAILABLE,
            limitation="no collaborator attached for branch continuation",
        )
        report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(
                through_position=cursor,
                external_boundaries=(boundary,),
            )
        )
        assert report.verified
        assert report.external_effects_skipped == 1
        assert report.external_boundaries == (boundary,)
        assert restored_state == {"value": "HELLO"}
        assert external_calls == 1
        assert not restarted.query_history_sync(
            RuntimeHistoryQuery(after_position=cursor, fact_type="message_accepted")
        ).facts
    finally:
        restarted.close()


def test_nested_replay_calls_do_not_grow_canonical_business_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"

    def parent_adapter(child_client: RuntimeClient) -> ExplicitComponentAdapter:
        descriptor = RuntimeActionBindingDescriptor(
            component_contract_id="component.test.replay_parent",
            action_id="component.test.replay_parent.restore",
            binding_id="binding.test.replay_parent.v1",
            binding_version=1,
            schema_version=1,
            request_codec_id="codec.test.replay_parent.request.json",
            result_codec_id="codec.test.replay_parent.result.json",
            failure_codec_id="codec.test.replay_parent.failure.json",
            idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
            replay_mode=RuntimeReplayMode.CANONICAL_EFFECT,
        )

        def replay(payload: JsonObject) -> None:
            child_client.request_sync(
                "component.test.counter.increment",
                {"amount": cast(int, payload["amount"])},
            )

        return ExplicitComponentAdapter(
            (
                ActionBinding(
                    descriptor=descriptor,
                    invoke=lambda amount: amount,
                    decode_request=lambda payload: ((cast(int, payload["amount"]),), {}),
                    encode_result=encode_json,
                    build_replay_effect=lambda args, _kwargs, _result: {
                        "amount": cast(int, args[0])
                    },
                    apply_replay_effect=replay,
                ),
            ),
            replay_state=ReplayStateBinding(
                is_empty=lambda: True,
                reset=lambda: None,
                import_checkpoint=lambda _reference: 0,
                export_state=lambda: {},
            ),
        )

    runtime = SqliteMessageRuntime.open(database, runtime_key="test.nested.replay")
    source_child = _Counter()
    child_registration = runtime.register_adapter(
        instance_key="test.counter.child",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(source_child),
    )
    child_address = runtime.address_for(child_registration.instance_key)
    source_child_client = RuntimeClient(
        runtime,
        source=child_address,
        target=child_address,
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )
    parent_registration = runtime.register_adapter(
        instance_key="test.replay_parent.primary",
        component_contract_id="component.test.replay_parent",
        adapter=parent_adapter(source_child_client),
    )
    parent_address = runtime.address_for(parent_registration.instance_key)
    source_parent_client = RuntimeClient(
        runtime,
        source=parent_address,
        target=parent_address,
        component_contract_id="component.test.replay_parent",
        request_codec_id="codec.test.replay_parent.request.json",
    )
    source_parent_client.request_sync("component.test.replay_parent.restore", {"amount": 6})
    cursor = runtime.current_position
    accepted_before = len(
        runtime.query_history_sync(RuntimeHistoryQuery(fact_type="message_accepted")).facts
    )
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.nested.replay")
    restored_child = _Counter()
    restored_child_registration = restarted.register_adapter(
        instance_key="test.counter.child",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(restored_child),
    )
    restored_child_address = restarted.address_for(restored_child_registration.instance_key)
    restored_child_client = RuntimeClient(
        restarted,
        source=restored_child_address,
        target=restored_child_address,
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )
    restarted.register_adapter(
        instance_key="test.replay_parent.primary",
        component_contract_id="component.test.replay_parent",
        adapter=parent_adapter(restored_child_client),
    )
    try:
        report = restarted.reconstruct_sync(RuntimeReconstructionRequest(through_position=cursor))
        assert report.verified
        assert restored_child.value == 6
        accepted_after = len(
            restarted.query_history_sync(RuntimeHistoryQuery(fact_type="message_accepted")).facts
        )
        assert accepted_after == accepted_before
        assert not restarted.query_history_sync(
            RuntimeHistoryQuery(
                after_position=cursor,
                fact_type="canonical_effect",
            )
        ).facts
    finally:
        restarted.close()


def test_replay_verification_may_use_runtime_messages_without_growing_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"

    def attach_counter(
        runtime: SqliteMessageRuntime,
        counter: _Counter,
    ) -> RuntimeClient:
        registration = runtime.declare_occurrence(
            ComponentOccurrenceDeclaration(
                instance_key="test.verifying_counter.primary",
                component_contract_id="component.test.verifying_counter",
                binding_id="binding.test.verifying_counter.v1",
                binding_version=1,
                replay_authority=RuntimeReplayMode.CANONICAL_EFFECT,
            )
        )
        address = runtime.address_for(registration.instance_key)
        client = RuntimeClient(
            runtime,
            source=address,
            target=address,
            component_contract_id="component.test.verifying_counter",
            request_codec_id="codec.test.verifying_counter.request.json",
        )
        increment_descriptor = RuntimeActionBindingDescriptor(
            component_contract_id="component.test.verifying_counter",
            action_id="component.test.verifying_counter.increment",
            binding_id="binding.test.verifying_counter.v1",
            binding_version=1,
            schema_version=1,
            request_codec_id="codec.test.verifying_counter.request.json",
            result_codec_id="codec.test.verifying_counter.result.json",
            failure_codec_id="codec.test.verifying_counter.failure.json",
            idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
            replay_mode=RuntimeReplayMode.CANONICAL_EFFECT,
        )
        read_descriptor = replace(
            increment_descriptor,
            action_id="component.test.verifying_counter.read",
            idempotency=RuntimeActionIdempotency.IDEMPOTENT,
            replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
        )

        def verify() -> tuple[str, ...]:
            outcome = client.request_sync("component.test.verifying_counter.read", {})
            if outcome.response.payload.value != {"result": counter.value}:
                return ("message-mediated state read did not match replayed state",)
            return ()

        runtime.attach_adapter(
            registration,
            ExplicitComponentAdapter(
                (
                    ActionBinding(
                        descriptor=increment_descriptor,
                        invoke=counter.increment,
                        decode_request=lambda payload: (
                            (cast(int, payload["amount"]),),
                            {},
                        ),
                        encode_result=encode_json,
                        build_replay_effect=lambda args, _kwargs, _result: {
                            "amount": cast(int, args[0])
                        },
                        apply_replay_effect=lambda payload: counter.increment(
                            cast(int, payload["amount"])
                        ),
                    ),
                    ActionBinding(
                        descriptor=read_descriptor,
                        invoke=lambda: counter.value,
                        decode_request=lambda _payload: ((), {}),
                        encode_result=encode_json,
                    ),
                ),
                replay_state=ReplayStateBinding(
                    is_empty=lambda: counter.value == 0,
                    reset=counter.reset,
                    import_checkpoint=lambda _reference: 0,
                    export_state=lambda: {"value": counter.value},
                    verify=verify,
                ),
            ),
        )
        return client

    runtime = SqliteMessageRuntime.open(database, runtime_key="test.replay.verification")
    source = _Counter()
    source_client = attach_counter(runtime, source)
    source_client.request_sync("component.test.verifying_counter.increment", {"amount": 8})
    cursor = runtime.current_position
    accepted_before = len(
        runtime.query_history_sync(RuntimeHistoryQuery(fact_type="message_accepted")).facts
    )
    runtime.close()

    restarted = SqliteMessageRuntime.open(
        database,
        runtime_key="test.replay.verification",
    )
    restored = _Counter()
    attach_counter(restarted, restored)
    try:
        report = restarted.reconstruct_sync(
            RuntimeReconstructionRequest(through_position=cursor)
        )
        assert report.verified
        assert restored.value == 8
        accepted_after = len(
            restarted.query_history_sync(
                RuntimeHistoryQuery(fact_type="message_accepted")
            ).facts
        )
        assert accepted_after == accepted_before
        assert not restarted.query_history_sync(
            RuntimeHistoryQuery(after_position=cursor, fact_type="message_accepted")
        ).facts
    finally:
        restarted.close()


def test_restart_requires_reconstruction_after_unconfirmed_terminal_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite"
    runtime, counter, client = _runtime_and_counter(database)
    runtime.simulate_ledger_failure_once("response_recorded")
    failed_envelope = client.envelope("component.test.counter.increment", {"amount": 1})
    with pytest.raises(RuntimeFailStopped):
        runtime.request_sync(failed_envelope)
    assert counter.value == 1
    runtime.close()

    restarted = SqliteMessageRuntime.open(database, runtime_key="test.runtime")
    restored = _Counter()
    registration = restarted.register_adapter(
        instance_key="test.counter.primary",
        component_contract_id="component.test.counter",
        adapter=_counter_adapter(restored),
    )
    address = restarted.address_for(registration.instance_key)
    restored_client = RuntimeClient(
        restarted,
        source=address,
        target=address,
        component_contract_id="component.test.counter",
        request_codec_id="codec.test.counter.request.json",
    )
    try:
        assert restarted.health == "recovery_required"
        with pytest.raises(RuntimeFailStopped, match="recovery_required"):
            restored_client.request_sync("component.test.counter.increment", {"amount": 1})
        report = restarted.reconstruct_sync(RuntimeReconstructionRequest())
        assert report.verified
        assert restored.value == 0
        assert restarted.health == "ready"
        recovered_outcome = restarted.request_sync(failed_envelope)
        assert recovered_outcome.response.kind is RuntimeMessageKind.FAULT
        assert recovered_outcome.trace_disposition is RuntimeTraceDisposition.INDETERMINATE
        assert restored.value == 0
        restored_client.request_sync("component.test.counter.increment", {"amount": 2})
        assert restored.value == 2
    finally:
        restarted.close()
