from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import cast

from components.rtg.route_pack.protocol import (
    JsonObject,
    JsonValue,
    RtgRoutePackAssemblyRequest,
    RtgRoutePackGateRecord,
    RtgRoutePackInvalid,
    RtgRoutePackRecord,
)

_DECISIONS = {"invoke", "clarify", "blocked"}


class DeterministicRtgRoutePackBuilder:
    """Deterministic read-only route-pack assembler."""

    def assemble(self, request: RtgRoutePackAssemblyRequest) -> RtgRoutePackRecord:
        hazards = tuple(_validate_hazard(hazard) for hazard in request.hazards)
        return cast(RtgRoutePackRecord, {
            "status": "needs_attention" if hazards else "ready",
            "intent": _validate_json_object(request.intent, "intent"),
            "selected_skill": _validate_json_object(request.selected_skill, "selected_skill"),
            "scoped_tools": _validate_json_object(request.scoped_tools, "scoped_tools"),
            "required_docs": _validate_text_tuple(request.required_docs, "required_docs"),
            "verification_commands": [
                _validate_json_object(command, "verification_command")
                for command in request.verification_commands
            ],
            "freshness_and_evidence": _validate_json_object(
                request.freshness_and_evidence,
                "freshness_and_evidence",
            ),
            "identity_and_citation_rules": _validate_json_object(
                request.identity_and_citation_rules,
                "identity_and_citation_rules",
            ),
            "single_graph_route": _validate_json_object(
                request.single_graph_route,
                "single_graph_route",
            ),
            "federated_plan": _validate_json_object(request.federated_plan, "federated_plan"),
            "graph_contexts": [
                _validate_json_object(context, "graph_context")
                for context in request.graph_contexts
            ],
            "hazards": list(hazards),
        })


class DeterministicRtgRoutePackGate:
    """Deterministic route-pack gate for agent execution decisions."""

    def evaluate(self, route_pack: RtgRoutePackRecord) -> RtgRoutePackGateRecord:
        normalized = _validate_route_pack(route_pack)
        hazards = _required_object_list(normalized, "hazards")
        blocking_hazards = [
            hazard for hazard in hazards if hazard.get("severity") == "blocker"
        ]
        clarification_hazards = [
            hazard for hazard in hazards if hazard.get("severity") != "blocker"
        ]
        if blocking_hazards:
            decision = "blocked"
            reason = "route pack contains blocker hazards"
        elif clarification_hazards:
            decision = "clarify"
            reason = "route pack requires confirmation before execution"
        else:
            decision = "invoke"
            reason = "route pack is ready for execution"
        return cast(RtgRoutePackGateRecord, {
            "decision": decision,
            "reason": reason,
            "intent": copy.deepcopy(normalized["intent"]),
            "route_pack_status": normalized["status"],
            "selected_skill": copy.deepcopy(normalized["selected_skill"]),
            "graph_targets": _graph_targets(normalized),
            "allowed_tools": _allowed_tools(normalized, decision=decision),
            "required_docs": copy.deepcopy(normalized["required_docs"]),
            "required_verification_commands": copy.deepcopy(
                normalized["verification_commands"]
            ),
            "freshness_and_evidence": _freshness_summary(normalized),
            "hazards": copy.deepcopy(hazards),
            "blocking_hazard_codes": _hazard_codes(blocking_hazards),
            "clarification_hazard_codes": _hazard_codes(clarification_hazards),
            "next_actions": _next_actions(
                normalized,
                decision=decision,
                blocking_hazards=blocking_hazards,
                clarification_hazards=clarification_hazards,
            ),
        })


class DeterministicRtgRoutePack:
    """Stateless realization of route-pack assembly and gate evaluation."""

    def assemble(self, request: RtgRoutePackAssemblyRequest) -> RtgRoutePackRecord:
        return DeterministicRtgRoutePackBuilder().assemble(request)

    def evaluate(self, route_pack: RtgRoutePackRecord) -> RtgRoutePackGateRecord:
        return DeterministicRtgRoutePackGate().evaluate(route_pack)


def _validate_route_pack(route_pack: JsonObject) -> JsonObject:
    pack = _validate_json_object(route_pack, "route_pack")
    status = _required_text(pack, "status")
    if status not in {"ready", "needs_attention"}:
        raise RtgRoutePackInvalid("route_pack.status must be ready or needs_attention")
    for key in (
        "intent",
        "selected_skill",
        "scoped_tools",
        "freshness_and_evidence",
        "identity_and_citation_rules",
        "single_graph_route",
        "federated_plan",
    ):
        _required_object(pack, key)
    _required_text_list(pack, "required_docs")
    _required_object_list(pack, "verification_commands")
    _required_object_list(pack, "graph_contexts")
    hazards = [_validate_hazard(hazard) for hazard in _required_object_list(pack, "hazards")]
    expected_status = "needs_attention" if hazards else "ready"
    if status != expected_status:
        raise RtgRoutePackInvalid(
            f"route_pack.status must be {expected_status} for the supplied hazards"
        )
    return pack


def _graph_targets(route_pack: JsonObject) -> JsonObject:
    route = _required_object(route_pack, "single_graph_route")
    plan = _required_object(route_pack, "federated_plan")
    return cast(JsonObject, {
        "selected_graph_id": route.get("selected_graph_id"),
        "candidate_graph_ids": [
            _required_text(candidate, "graph_id")
            for candidate in _object_list(route.get("candidates", []), "route.candidates")
        ],
        "planned_graph_ids": [
            _required_text(step, "graph_id")
            for step in _object_list(plan.get("steps", []), "plan.steps")
        ],
        "graph_context_ids": [
            _required_text(context, "graph_id")
            for context in _required_object_list(route_pack, "graph_contexts")
        ],
        "single_graph_requires_confirmation": _required_bool(
            route,
            "requires_confirmation",
        ),
        "federated_plan_requires_confirmation": _required_bool(
            plan,
            "requires_confirmation",
        ),
    })


def _allowed_tools(route_pack: JsonObject, *, decision: str) -> JsonObject:
    if decision not in _DECISIONS:
        raise RtgRoutePackInvalid("decision must be invoke, clarify, or blocked")
    scoped_tools = _required_object(route_pack, "scoped_tools")
    return cast(JsonObject, {
        "federation_mcp_tools": _required_text_list(scoped_tools, "federation_mcp_tools"),
        "graph_local_mcp_tools_after_selection": (
            _required_text_list(scoped_tools, "graph_local_mcp_tools_after_selection")
            if decision == "invoke"
            else []
        ),
        "just_recipes": _required_text_list(scoped_tools, "just_recipes"),
    })


def _freshness_summary(route_pack: JsonObject) -> JsonObject:
    freshness = _required_object(route_pack, "freshness_and_evidence")
    preflight = _required_object(freshness, "preflight")
    capabilities = _required_object(freshness, "capabilities")
    summary = cast(JsonObject, {
        "preflight_status": _required_text(preflight, "status"),
        "ready_capability_count": capabilities.get("ready_capability_count"),
        "repo_twin_queries": _required_text_list(freshness, "repo_twin_queries"),
    })
    direct_read = freshness.get("direct_read")
    if isinstance(direct_read, dict):
        summary["direct_read"] = copy.deepcopy(direct_read)
    stale_recovery = freshness.get("stale_recovery_command")
    if isinstance(stale_recovery, str):
        summary["stale_recovery_command"] = stale_recovery
    return summary


def _hazard_codes(hazards: list[JsonObject]) -> list[str]:
    return [_required_text(hazard, "code") for hazard in hazards]


def _next_actions(
    route_pack: JsonObject,
    *,
    decision: str,
    blocking_hazards: list[JsonObject],
    clarification_hazards: list[JsonObject],
) -> list[JsonObject]:
    if decision == "blocked":
        return [
            cast(JsonObject, {
                "action": "stop",
                "reason": str(hazard.get("message", hazard.get("code", "blocker hazard"))),
            })
            for hazard in blocking_hazards
        ]
    if decision == "clarify":
        return [
            cast(JsonObject, {
                "action": "confirm_or_recompile_route",
                "reason": str(
                    hazard.get("message", hazard.get("code", "route requires confirmation"))
                ),
            })
            for hazard in clarification_hazards
        ]
    route = _required_object(route_pack, "single_graph_route")
    plan = _required_object(route_pack, "federated_plan")
    actions: list[JsonObject] = [
        cast(JsonObject, {
            "action": "run_verification_commands",
            "commands": [
                _required_text(command, "command")
                for command in _required_object_list(route_pack, "verification_commands")
            ],
        })
    ]
    direct_read = _direct_read_action(route_pack)
    if direct_read is not None:
        actions.append(direct_read)
        return actions
    graph_contexts = _required_object_list(route_pack, "graph_contexts")
    if len(graph_contexts) > 1:
        actions.append(
            cast(JsonObject, {
                "action": "execute_federated_read_plan",
                "graph_ids": [_required_text(context, "graph_id") for context in graph_contexts],
            })
        )
        return actions
    selected_graph_id = route.get("selected_graph_id")
    if isinstance(selected_graph_id, str):
        actions.append(
            cast(JsonObject, {
                "action": "handoff_to_graph_local_mcp",
                "graph_id": selected_graph_id,
                "tool": "vellis_graph_mcp_info",
            })
        )
    else:
        planned_graph_ids = [
            _required_text(step, "graph_id")
            for step in _object_list(plan.get("steps", []), "plan.steps")
        ]
        if planned_graph_ids:
            actions.append(
                cast(JsonObject, {
                    "action": "execute_federated_read_plan",
                    "graph_ids": planned_graph_ids,
                    "tool": "vellis_federated_answer",
                })
            )
    return actions


def _direct_read_action(route_pack: JsonObject) -> JsonObject | None:
    contexts = _required_object_list(route_pack, "graph_contexts")
    if len(contexts) != 1:
        return None
    freshness = _required_object(route_pack, "freshness_and_evidence")
    profile = freshness.get("direct_read")
    if not isinstance(profile, dict):
        return None
    graph_id = _required_text(profile, "graph_id")
    if _required_text(contexts[0], "graph_id") != graph_id:
        raise RtgRoutePackInvalid("direct_read graph_id must match the sole graph context")
    return cast(JsonObject, {
        "action": "execute_descriptor_read",
        "graph_id": graph_id,
        "query_name": _required_text(profile, "query_name"),
        "command": _required_text(profile, "command"),
    })


def _validate_json_object(value: object, name: str) -> JsonObject:
    copied = _normalize_json_value(value)
    if not isinstance(copied, dict):
        raise RtgRoutePackInvalid(f"{name} must be a JSON object")
    return copied


def _validate_hazard(value: object) -> JsonObject:
    hazard = _validate_json_object(value, "hazard")
    _required_text(hazard, "code")
    _required_text(hazard, "severity")
    _required_text(hazard, "message")
    return hazard


def _normalize_json_value(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        normalized: JsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RtgRoutePackInvalid("JSON object keys must be strings")
            normalized[key] = _normalize_json_value(item)
        return normalized
    if isinstance(value, list | tuple):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise RtgRoutePackInvalid("JSON numbers must be finite")
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise RtgRoutePackInvalid("JSON values must be serializable")


def _validate_text_tuple(values: tuple[str, ...], name: str) -> list[str]:
    if not isinstance(values, tuple):
        raise RtgRoutePackInvalid(f"{name} must be a tuple")
    return [_validate_text(value, name) for value in values]


def _required_object(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RtgRoutePackInvalid(f"{key} must be a JSON object")
    return _validate_json_object(value, key)


def _required_object_list(payload: JsonObject, key: str) -> list[JsonObject]:
    return _object_list(payload.get(key), key)


def _object_list(value: JsonValue | object, name: str) -> list[JsonObject]:
    if not isinstance(value, list):
        raise RtgRoutePackInvalid(f"{name} must be a list of JSON objects")
    return [_validate_json_object(item, name) for item in value]


def _required_text_list(payload: JsonObject, key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise RtgRoutePackInvalid(f"{key} must be a list of strings")
    return [_validate_text(item, key) for item in value]


def _required_text(payload: JsonObject, key: str) -> str:
    return _validate_text(payload.get(key), key)


def _required_bool(payload: JsonObject, key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise RtgRoutePackInvalid(f"{key} must be a boolean")
    return value


def _validate_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgRoutePackInvalid(f"{name} must be a non-empty string")
    return value.strip()
