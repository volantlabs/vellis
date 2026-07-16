from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    RtgChangeReference,
    RtgGraphAnchorWrite,
    RtgGraphChangeSet,
    RtgGraphLinkWrite,
    create_rtg_change_validator_adapter,
)
from components.rtg.constraints import InMemoryRtgConstraints, create_rtg_constraints_adapter
from components.rtg.controller import (
    RTG_CONTROLLER_ACTIONS,
    RtgControllerCoordinator,
    RtgControllerOperationResult,
    create_rtg_controller_adapter,
)
from components.rtg.graph import (
    RTG_GRAPH_ACTIONS,
    InMemoryRtgGraph,
    RtgTypeCountList,
    create_rtg_graph_adapter,
)
from components.rtg.migration import InMemoryRtgMigration, create_rtg_migration_adapter
from components.rtg.query import SimpleRtgQueryEngine, create_rtg_query_adapter
from components.rtg.schema import InMemoryRtgSchema, create_rtg_schema_adapter
from components.runtime.component_adapter import ComponentAdapter, ComponentEndpoint, decode_typed
from components.runtime.message_runtime import SqliteMessageRuntime
from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    RuntimeLaneDeclaration,
    RuntimeMessageKind,
    RuntimeReplayMode,
    RuntimeTopologyManifest,
    topology_manifest_hash,
)
from components.storage.json_file import LocalJsonFileStorage, create_json_file_storage_adapter


def test_controller_coordinates_leaf_occurrences_without_business_object_injection(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime = SqliteMessageRuntime(tmp_path / "runtime.sqlite", runtime_key="test.controller")
        participants = {
            "vellis.graph.primary": create_rtg_graph_adapter(InMemoryRtgGraph.empty()),
            "vellis.schema.primary": create_rtg_schema_adapter(InMemoryRtgSchema.empty()),
            "vellis.constraints.primary": create_rtg_constraints_adapter(
                InMemoryRtgConstraints.empty()
            ),
            "vellis.migration.primary": create_rtg_migration_adapter(InMemoryRtgMigration.empty()),
            "vellis.query.primary": create_rtg_query_adapter(SimpleRtgQueryEngine()),
            "vellis.validation.primary": create_rtg_change_validator_adapter(
                DeterministicRtgChangeValidator()
            ),
            "vellis.storage.json.primary": create_json_file_storage_adapter(
                LocalJsonFileStorage.open(tmp_path / "documents")
            ),
            "vellis.controller.primary": create_rtg_controller_adapter(RtgControllerCoordinator()),
            "ingress": ComponentAdapter(
                binding_id="binding.test.ingress",
                component_contract_id="component.test.ingress",
            ),
        }
        declarations = tuple(
            ComponentOccurrenceDeclaration(
                instance_key=key,
                component_contract_id=adapter.describe().component_contract_id,
                binding_id=adapter.describe().binding_id,
                binding_version=adapter.describe().binding_version,
                lanes=(
                    (
                        RuntimeLaneDeclaration("read", worker_limit=4),
                        RuntimeLaneDeclaration("mutation"),
                    )
                    if key == "vellis.controller.primary"
                    else (RuntimeLaneDeclaration("serialized"),)
                ),
                replay_authority=(
                    RuntimeReplayMode.CANONICAL_EFFECT
                    if key
                    in {
                        "vellis.graph.primary",
                        "vellis.schema.primary",
                        "vellis.constraints.primary",
                        "vellis.migration.primary",
                    }
                    else RuntimeReplayMode.NO_STATE_EFFECT
                ),
            )
            for key, adapter in participants.items()
        )
        manifest = RuntimeTopologyManifest("test.controller", 4, declarations, (), "")
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        await runtime.prepare_static_topology(manifest)
        for declaration in declarations:
            registration = await runtime.register_occurrence(declaration)
            participant = participants[declaration.instance_key]
            await runtime.attach_participant(
                registration,
                participant,
                participant.describe().actions,
            )
        await runtime.confirm_static_topology(manifest)
        ingress = participants["ingress"]
        endpoint = ComponentEndpoint(
            runtime,
            ingress,
            source=runtime.address_for("ingress"),
        )
        outcome = await endpoint.request(
            RTG_CONTROLLER_ACTIONS["apply_live_graph_changes"],
            {
                "graph_changes": RtgGraphChangeSet(
                    anchor_writes=(
                        RtgGraphAnchorWrite(
                            RtgChangeReference(local_ref="person"),
                            "Person",
                        ),
                    )
                ),
                "validation_mode": "skip",
            },
            target=runtime.address_for("vellis.controller.primary"),
        )
        payload = outcome.response.payload.value
        assert isinstance(payload, dict)
        result = decode_typed(payload["result"], RtgControllerOperationResult)
        assert isinstance(result, RtgControllerOperationResult)
        assert result.status == "applied"
        assert set(result.generated_ids) == {"person"}

        trace = await runtime.get_trace(outcome.request.trace_id, include_payload=True)
        targets = {
            fact.instance_key for fact in trace.facts if fact.fact_type == "delivery_started"
        }
        assert "vellis.controller.primary" in targets
        assert "vellis.graph.primary" in targets
        assert targets.isdisjoint(
            {
                "vellis.schema.primary",
                "vellis.constraints.primary",
                "vellis.migration.primary",
            }
        )
        assert (
            len(
                {
                    fact.envelope.message_id
                    for fact in trace.facts
                    if fact.action_id == "component.rtg.graph.apply_batch"
                    and fact.fact_type == "message_accepted"
                    and fact.envelope is not None
                    and fact.envelope.kind is RuntimeMessageKind.REQUEST
                }
            )
            == 1
        )
        assert not any(fact.action_id and "snapshot" in fact.action_id for fact in trace.facts)
        assert not any(fact.action_id and "compensation" in fact.action_id for fact in trace.facts)

        failed = await endpoint.request(
            RTG_CONTROLLER_ACTIONS["apply_live_graph_changes"],
            {
                "graph_changes": RtgGraphChangeSet(
                    anchor_writes=(
                        RtgGraphAnchorWrite(RtgChangeReference(local_ref="temp"), "Temp"),
                    ),
                    link_writes=(
                        RtgGraphLinkWrite(
                            RtgChangeReference(local_ref="bad-link"),
                            "missing_endpoint",
                            RtgChangeReference(resource_id=uuid4()),
                            RtgChangeReference(resource_id=uuid4()),
                        ),
                    ),
                ),
                "validation_mode": "skip",
            },
            target=runtime.address_for("vellis.controller.primary"),
        )
        assert failed.response.kind is RuntimeMessageKind.FAULT
        failed_trace = await runtime.get_trace(failed.request.trace_id, include_payload=True)
        assert failed_trace.disposition is not None
        assert failed_trace.disposition.value == "aborted"
        assert (
            len(
                {
                    fact.envelope.message_id
                    for fact in failed_trace.facts
                    if fact.action_id == "component.rtg.graph.apply_batch"
                    and fact.fact_type == "message_accepted"
                    and fact.envelope is not None
                    and fact.envelope.kind is RuntimeMessageKind.REQUEST
                }
            )
            == 1
        )
        assert not any(
            fact.action_id and "compensation" in fact.action_id for fact in failed_trace.facts
        )
        assert not any(
            fact.action_id and "snapshot" in fact.action_id for fact in failed_trace.facts
        )
        counts = await endpoint.request(
            RTG_GRAPH_ACTIONS["count_by_type"],
            {"kind": None, "live": None},
            target=runtime.address_for("vellis.graph.primary"),
        )
        counts_payload = counts.response.payload.value
        assert isinstance(counts_payload, dict)
        type_counts = decode_typed(counts_payload["result"], RtgTypeCountList)
        assert all(item.type != "Temp" for item in type_counts.counts)
        await runtime.aclose()

    asyncio.run(exercise())


MODEL_EVIDENCE = {
    "RtgControllerRoutineWorkScalingVerification": (
        "test_controller_coordinates_leaf_occurrences_without_business_object_injection",
    ),
}
