from __future__ import annotations

import copy
from dataclasses import replace
from typing import cast

import pytest

from components.rtg.route_pack import (
    DeterministicRtgRoutePack,
    DeterministicRtgRoutePackBuilder,
    DeterministicRtgRoutePackGate,
    JsonObject,
    JsonValue,
    RtgRoutePackAssemblyRequest,
    RtgRoutePackInvalid,
)
from components.rtg.route_pack.reference import (
    create_reference_builder,
    create_reference_component,
    create_reference_gate,
)

MODEL_EVIDENCE = {
    "AssembleRoutePackContractVerification": (
        "test_assemble_ready_pack_and_invoke_gate_preserve_inputs",
        "test_warning_hazard_clarifies_and_hides_graph_local_tools",
        "test_blocker_hazard_blocks_and_reports_blocker_code",
        "test_assemble_rejects_non_finite_and_malformed_json",
    ),
    "EvaluateRoutePackContractVerification": (
        "test_assemble_ready_pack_and_invoke_gate_preserve_inputs",
        "test_invoke_uses_descriptor_read_without_graph_local_handoff",
        "test_invoke_uses_federated_plan_for_multiple_graph_contexts",
        "test_warning_hazard_clarifies_and_hides_graph_local_tools",
        "test_blocker_hazard_blocks_and_reports_blocker_code",
        "test_gate_rejects_malformed_route_pack",
        "test_gate_rejects_status_hazard_inconsistency_and_malformed_hazard",
    ),
    "RtgRoutePackBoundaryVerification": (
        "test_assemble_ready_pack_and_invoke_gate_preserve_inputs",
        "test_invoke_uses_descriptor_read_without_graph_local_handoff",
        "test_invoke_uses_federated_plan_for_multiple_graph_contexts",
        "test_warning_hazard_clarifies_and_hides_graph_local_tools",
        "test_blocker_hazard_blocks_and_reports_blocker_code",
        "test_reference_factories_expose_split_stateless_realization",
        "test_route_pack_surfaces_do_not_expose_execution_operations",
    ),
}


def pack_request(
    *,
    hazards: tuple[JsonObject, ...] = (),
    selected_graph_id: str | None = "repo_twin",
) -> RtgRoutePackAssemblyRequest:
    return RtgRoutePackAssemblyRequest(
        intent={
            "text": "Compare component evidence.",
            "operation": "read",
            "target_graph_ids": [],
            "domain_hints": [],
            "tag_hints": [],
        },
        selected_skill={
            "name": "rtg-federation-control-plane",
            "path": ".agents/skills/rtg-federation-control-plane/SKILL.md",
            "handoff_chain": [
                {
                    "name": "rtg-knowledge-graph-mcp",
                    "path": ".agents/skills/rtg-knowledge-graph-mcp/SKILL.md",
                    "when": "after graph selection",
                }
            ],
        },
        scoped_tools={
            "federation_mcp_tools": ["vellis_route_pack_preview", "vellis_route_pack_gate"],
            "graph_local_mcp_tools_after_selection": [
                "rtg_validate_graph",
                "rtg_execute_query",
            ],
            "just_recipes": ["just rtg-route-pack-gate"],
        },
        required_docs=("docs/rtg-monographs/README.md",),
        verification_commands=(
            {
                "command": "just rtg-federation-preflight",
                "when": "before execution",
            },
        ),
        freshness_and_evidence={
            "preflight": {"status": "passed"},
            "capabilities": {"ready_capability_count": 1},
            "repo_twin_queries": ["just graph-query evidence component.rtg.graph_registry"],
        },
        identity_and_citation_rules={"canonical_identity": "(graph_id, local_uuid)"},
        single_graph_route={
            "selected_graph_id": selected_graph_id,
            "requires_confirmation": selected_graph_id is None,
            "candidates": [{"graph_id": "repo_twin", "score": 0.9, "reasons": ["domain:repo"]}],
        },
        federated_plan={
            "requires_confirmation": False,
            "steps": [{"graph_id": "repo_twin", "operation": "read", "score": 0.9}],
        },
        graph_contexts=(
            {
                "graph_id": "repo_twin",
                "capabilities": {"status": "ready"},
                "preflight": {"status": "ready"},
            },
        ),
        hazards=hazards,
    )


def test_assemble_ready_pack_and_invoke_gate_preserve_inputs() -> None:
    request = pack_request()
    original = copy.deepcopy(request)
    builder = DeterministicRtgRoutePackBuilder()
    gate = DeterministicRtgRoutePackGate()

    route_pack = builder.assemble(request)
    decision = gate.evaluate(route_pack)

    assert route_pack["status"] == "ready"
    assert decision["decision"] == "invoke"
    assert decision["reason"] == "route pack is ready for execution"
    assert json_object_field(decision, "graph_targets")["selected_graph_id"] == "repo_twin"
    assert json_object_field(decision, "allowed_tools")[
        "graph_local_mcp_tools_after_selection"
    ] == [
        "rtg_validate_graph",
        "rtg_execute_query",
    ]
    assert json_object_list_field(decision, "next_actions")[0]["action"] == (
        "run_verification_commands"
    )
    assert request == original


def test_invoke_uses_descriptor_read_without_graph_local_handoff() -> None:
    request = pack_request()
    request.freshness_and_evidence["direct_read"] = {
        "graph_id": "repo_twin",
        "query_name": "repo_components_evidence_status",
        "command": "just graph-query untested",
        "verification_commands": ["just graph-check"],
        "required_docs": [],
        "stale_recovery_command": "just graph-verify",
    }
    request.freshness_and_evidence["stale_recovery_command"] = "just graph-verify"
    request.scoped_tools["graph_local_mcp_tools_after_selection"] = []

    route_pack = DeterministicRtgRoutePackBuilder().assemble(request)
    decision = DeterministicRtgRoutePackGate().evaluate(route_pack)

    assert decision["next_actions"] == [
        {
            "action": "run_verification_commands",
            "commands": ["just rtg-federation-preflight"],
        },
        {
            "action": "execute_descriptor_read",
            "graph_id": "repo_twin",
            "query_name": "repo_components_evidence_status",
            "command": "just graph-query untested",
        },
    ]
    assert (
        json_object_field(decision, "freshness_and_evidence")["stale_recovery_command"]
        == "just graph-verify"
    )


def test_invoke_uses_federated_plan_for_multiple_graph_contexts() -> None:
    request = replace(
        pack_request(),
        graph_contexts=(
            {
                "graph_id": "repo_twin",
                "capabilities": {"status": "ready"},
                "preflight": {"status": "ready"},
            },
            {
                "graph_id": "personal_ops",
                "capabilities": {"status": "ready"},
                "preflight": {"status": "ready"},
            },
        ),
    )

    route_pack = DeterministicRtgRoutePackBuilder().assemble(request)
    decision = DeterministicRtgRoutePackGate().evaluate(route_pack)

    assert json_object_list_field(decision, "next_actions")[1] == {
        "action": "execute_federated_read_plan",
        "graph_ids": ["repo_twin", "personal_ops"],
    }


def test_warning_hazard_clarifies_and_hides_graph_local_tools() -> None:
    route_pack = DeterministicRtgRoutePackBuilder().assemble(
        pack_request(
            hazards=(
                {
                    "code": "single_graph_route_requires_confirmation",
                    "severity": "warning",
                    "message": "multiple graphs tied",
                },
            ),
            selected_graph_id=None,
        )
    )

    decision = DeterministicRtgRoutePackGate().evaluate(route_pack)

    assert route_pack["status"] == "needs_attention"
    assert decision["decision"] == "clarify"
    assert decision["clarification_hazard_codes"] == ["single_graph_route_requires_confirmation"]
    assert decision["blocking_hazard_codes"] == []
    assert (
        json_object_field(decision, "allowed_tools")["graph_local_mcp_tools_after_selection"] == []
    )
    assert decision["next_actions"] == [
        {
            "action": "confirm_or_recompile_route",
            "reason": "multiple graphs tied",
        }
    ]


def test_blocker_hazard_blocks_and_reports_blocker_code() -> None:
    route_pack = DeterministicRtgRoutePackBuilder().assemble(
        pack_request(
            hazards=(
                {
                    "code": "write_target_required",
                    "severity": "blocker",
                    "message": "writes require explicit targets",
                },
                {
                    "code": "single_graph_route_requires_confirmation",
                    "severity": "warning",
                    "message": "write route needs confirmation",
                },
            ),
            selected_graph_id=None,
        )
    )

    decision = DeterministicRtgRoutePackGate().evaluate(route_pack)

    assert decision["decision"] == "blocked"
    assert decision["blocking_hazard_codes"] == ["write_target_required"]
    assert decision["clarification_hazard_codes"] == ["single_graph_route_requires_confirmation"]
    assert (
        json_object_field(decision, "allowed_tools")["graph_local_mcp_tools_after_selection"] == []
    )
    assert decision["next_actions"] == [
        {
            "action": "stop",
            "reason": "writes require explicit targets",
        }
    ]


def test_gate_rejects_malformed_route_pack() -> None:
    with pytest.raises(RtgRoutePackInvalid, match="route_pack.status"):
        DeterministicRtgRoutePackGate().evaluate({"status": "maybe"})


@pytest.mark.parametrize("value", (float("nan"), float("inf"), object()))
def test_assemble_rejects_non_finite_and_malformed_json(value: object) -> None:
    request = pack_request()
    request.intent["bad"] = value  # type: ignore[assignment]

    with pytest.raises(RtgRoutePackInvalid, match="JSON"):
        DeterministicRtgRoutePackBuilder().assemble(request)


def test_gate_rejects_status_hazard_inconsistency_and_malformed_hazard() -> None:
    ready = DeterministicRtgRoutePackBuilder().assemble(pack_request())
    ready["status"] = "needs_attention"
    with pytest.raises(RtgRoutePackInvalid, match="supplied hazards"):
        DeterministicRtgRoutePackGate().evaluate(ready)

    malformed = DeterministicRtgRoutePackBuilder().assemble(pack_request())
    malformed["status"] = "needs_attention"
    malformed["hazards"] = [{"code": "missing_message", "severity": "warning"}]
    with pytest.raises(RtgRoutePackInvalid, match="message"):
        DeterministicRtgRoutePackGate().evaluate(malformed)


def test_reference_factories_expose_split_stateless_realization() -> None:
    component = create_reference_component()
    request = pack_request()
    assert isinstance(component, DeterministicRtgRoutePack)
    assert component.evaluate(component.assemble(request))["decision"] == "invoke"
    assert isinstance(create_reference_builder(), DeterministicRtgRoutePackBuilder)
    assert isinstance(create_reference_gate(), DeterministicRtgRoutePackGate)


def test_route_pack_surfaces_do_not_expose_execution_operations() -> None:
    builder = DeterministicRtgRoutePackBuilder()
    gate = DeterministicRtgRoutePackGate()

    for surface in (builder, gate):
        assert not hasattr(surface, "execute")
        assert not hasattr(surface, "query")
        assert not hasattr(surface, "write")
        assert not hasattr(surface, "traverse_bridge")


def json_object_field(payload: JsonObject, key: str) -> JsonObject:
    value = payload[key]
    assert isinstance(value, dict)
    return cast(JsonObject, value)


def json_object_list_field(payload: JsonObject, key: str) -> list[JsonObject]:
    value = payload[key]
    assert isinstance(value, list)
    return [json_object_value(item) for item in value]


def json_object_value(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return cast(JsonObject, value)
