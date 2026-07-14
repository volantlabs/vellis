from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apps.rtg_federation.registry_io import (
    DEFAULT_REGISTRY_PATH,
    default_bridge_path_for_registry,
    load_optional_bridge_store,
    load_registry,
    route_pack_gate_payload,
    route_pack_preview_payload,
)
from components.rtg.graph_bridge import RtgGraphBridge
from components.rtg.graph_registry import (
    RtgGraphFederatedIntent,
    RtgGraphIntent,
    RtgGraphRegistry,
    RtgGraphRegistryError,
)

DEFAULT_CASES_PATH = Path("docs/guides/vellis/evals/rtg-federation-routing-cases.json")
SUPPORTED_MODES = {"route", "federated_plan", "route_pack_gate", "route_pack_preview"}
SUPPORTED_OPERATIONS = {"read", "write", "admin"}
ROUTE_EXPECTED_FIELDS = {
    "selected_graph_id",
    "requires_confirmation",
    "candidate_graph_ids",
    "reason",
}
PLAN_EXPECTED_FIELDS = {
    "step_graph_ids",
    "requires_confirmation",
    "executable",
    "reason",
}
ROUTE_PACK_EXPECTED_FIELDS = {
    "status",
    "selected_skill_name",
    "handoff_skill_names",
    "graph_ids",
    "hazard_codes",
    "preflight_status",
    "selected_graph_id",
    "single_graph_requires_confirmation",
    "federated_plan_requires_confirmation",
    "verification_commands",
}
ROUTE_PACK_GATE_EXPECTED_FIELDS = {
    "decision",
    "route_pack_status",
    "selected_skill_name",
    "selected_graph_id",
    "graph_context_ids",
    "blocking_hazard_codes",
    "clarification_hazard_codes",
    "preflight_status",
    "allowed_federation_tools",
    "allowed_graph_local_tools",
    "required_verification_commands",
}
EXPECTED_FIELDS_BY_MODE = {
    "route": ROUTE_EXPECTED_FIELDS,
    "federated_plan": PLAN_EXPECTED_FIELDS,
    "route_pack_gate": ROUTE_PACK_GATE_EXPECTED_FIELDS,
    "route_pack_preview": ROUTE_PACK_EXPECTED_FIELDS,
}


class RtgFederationEvalInvalid(ValueError):
    """A routing evaluation matrix is malformed."""


def evaluate_routing_matrix(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cases_path: Path = DEFAULT_CASES_PATH,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    bridge_store = load_optional_bridge_store(default_bridge_path_for_registry(registry_path))
    preflight = _routing_eval_preflight(registry)
    payload = _load_matrix(cases_path)
    results = tuple(
        _evaluate_case(
            registry,
            case,
            bridge_store=bridge_store,
            preflight_override=preflight,
        )
        for case in payload["cases"]
    )
    failed_case_ids = [result["case_id"] for result in results if result["status"] == "failed"]
    return {
        "status": "passed" if not failed_case_ids else "failed",
        "matrix_version": payload["version"],
        "registry_path": str(registry_path),
        "cases_path": str(cases_path),
        "case_count": len(results),
        "passed_case_count": len(results) - len(failed_case_ids),
        "failed_case_count": len(failed_case_ids),
        "failed_case_ids": failed_case_ids,
        "cases": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rtg_federation_eval")
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help="Path to an RTG monograph registry JSON file.",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to a federation routing case matrix JSON file.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        result = evaluate_routing_matrix(registry_path=args.registry, cases_path=args.cases)
    except (
        OSError,
        json.JSONDecodeError,
        RtgGraphRegistryError,
        RtgFederationEvalInvalid,
    ) as error:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "invalid",
                        "error": {"type": type(error).__name__, "message": str(error)},
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"status=invalid error={type(error).__name__}: {error}")
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"status={result['status']} cases={result['case_count']} "
            f"passed={result['passed_case_count']} failed={result['failed_case_count']}"
        )
        for case in result["cases"]:
            print(f"- {case['case_id']} mode={case['mode']} status={case['status']}")
            for mismatch in case["mismatches"]:
                print(
                    f"  {mismatch['field']}: expected={mismatch['expected']!r} "
                    f"actual={mismatch['actual']!r}"
                )
    return 0 if result["status"] == "passed" else 1


def _load_matrix(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RtgFederationEvalInvalid("routing matrix root must be an object")
    version = payload.get("version")
    if version != 1:
        raise RtgFederationEvalInvalid("routing matrix version must be 1")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RtgFederationEvalInvalid("routing matrix cases must be a non-empty list")
    normalized_cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        normalized = _normalize_case(case, index=index)
        case_id = normalized["case_id"]
        if case_id in seen:
            raise RtgFederationEvalInvalid(f"duplicate routing matrix case_id: {case_id}")
        seen.add(case_id)
        normalized_cases.append(normalized)
    return {"version": version, "cases": normalized_cases}


def _normalize_case(payload: object, *, index: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RtgFederationEvalInvalid(f"routing matrix case {index} must be an object")
    case_id = _required_str(payload, "case_id", index=index)
    category = _required_str(payload, "category", index=index)
    mode = _required_str(payload, "mode", index=index)
    if mode not in SUPPORTED_MODES:
        raise RtgFederationEvalInvalid(
            f"routing matrix case {case_id} mode must be one of {sorted(SUPPORTED_MODES)}"
        )
    intent = payload.get("intent")
    if not isinstance(intent, dict):
        raise RtgFederationEvalInvalid(f"routing matrix case {case_id} intent must be an object")
    operation = intent.get("operation", "read")
    if not isinstance(operation, str) or operation not in SUPPORTED_OPERATIONS:
        raise RtgFederationEvalInvalid(
            f"routing matrix case {case_id} operation must be one of "
            f"{sorted(SUPPORTED_OPERATIONS)}"
        )
    text = intent.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RtgFederationEvalInvalid(
            f"routing matrix case {case_id} intent.text must be a non-empty string"
        )
    expected = payload.get("expected")
    if not isinstance(expected, dict):
        raise RtgFederationEvalInvalid(f"routing matrix case {case_id} expected must be an object")
    allowed_fields = EXPECTED_FIELDS_BY_MODE[mode]
    unknown_fields = sorted(set(expected) - allowed_fields)
    if unknown_fields:
        raise RtgFederationEvalInvalid(
            f"routing matrix case {case_id} has unsupported expected fields: "
            f"{', '.join(unknown_fields)}"
        )
    if not expected:
        raise RtgFederationEvalInvalid(
            f"routing matrix case {case_id} expected must contain at least one field"
        )
    return {
        "case_id": case_id,
        "category": category,
        "mode": mode,
        "intent": {
            "operation": operation,
            "text": text.strip(),
            "target_graph_id": _optional_str(intent, "target_graph_id", case_id=case_id),
            "target_graph_ids": _str_list(intent, "target_graph_ids", case_id=case_id),
            "domain_hints": _str_list(intent, "domain_hints", case_id=case_id),
            "tag_hints": _str_list(intent, "tag_hints", case_id=case_id),
        },
        "expected": expected,
    }


def _evaluate_case(
    registry: RtgGraphRegistry,
    case: dict[str, Any],
    *,
    bridge_store: RtgGraphBridge | None,
    preflight_override: dict[str, Any],
) -> dict[str, Any]:
    intent = case["intent"]
    if case["mode"] == "route":
        route = registry.compile_intent(
            RtgGraphIntent(
                operation=intent["operation"],
                text=intent["text"],
                target_graph_id=intent["target_graph_id"],
                domain_hints=tuple(intent["domain_hints"]),
                tag_hints=tuple(intent["tag_hints"]),
            )
        )
        actual: dict[str, Any] = {
            "selected_graph_id": route.selected_graph_id,
            "requires_confirmation": route.requires_confirmation,
            "candidate_graph_ids": [candidate.graph_id for candidate in route.candidates],
            "reason": route.reason,
        }
    elif case["mode"] == "federated_plan":
        plan = registry.compile_federated_intent(
            RtgGraphFederatedIntent(
                operation=intent["operation"],
                text=intent["text"],
                target_graph_ids=tuple(intent["target_graph_ids"]),
                domain_hints=tuple(intent["domain_hints"]),
                tag_hints=tuple(intent["tag_hints"]),
            )
        )
        actual = {
            "step_graph_ids": [step.graph_id for step in plan.steps],
            "requires_confirmation": plan.requires_confirmation,
            "executable": plan.executable,
            "reason": plan.reason,
        }
    elif case["mode"] == "route_pack_preview":
        route_pack = route_pack_preview_payload(
            registry,
            text=intent["text"],
            operation=intent["operation"],
            target_graph_ids=tuple(intent["target_graph_ids"]),
            domain_hints=tuple(intent["domain_hints"]),
            tag_hints=tuple(intent["tag_hints"]),
            bridge_store=bridge_store,
            preflight_override=preflight_override,
        )
        actual = {
            "status": route_pack["status"],
            "selected_skill_name": route_pack["selected_skill"]["name"],
            "handoff_skill_names": [
                handoff["name"] for handoff in route_pack["selected_skill"]["handoff_chain"]
            ],
            "graph_ids": [context["graph_id"] for context in route_pack["graph_contexts"]],
            "hazard_codes": [hazard["code"] for hazard in route_pack["hazards"]],
            "preflight_status": route_pack["freshness_and_evidence"]["preflight"]["status"],
            "selected_graph_id": route_pack["single_graph_route"]["selected_graph_id"],
            "single_graph_requires_confirmation": route_pack["single_graph_route"][
                "requires_confirmation"
            ],
            "federated_plan_requires_confirmation": route_pack["federated_plan"][
                "requires_confirmation"
            ],
            "verification_commands": [
                command["command"] for command in route_pack["verification_commands"]
            ],
        }
    else:
        gate = route_pack_gate_payload(
            registry,
            text=intent["text"],
            operation=intent["operation"],
            target_graph_ids=tuple(intent["target_graph_ids"]),
            domain_hints=tuple(intent["domain_hints"]),
            tag_hints=tuple(intent["tag_hints"]),
            bridge_store=bridge_store,
            preflight_override=preflight_override,
        )
        actual = {
            "decision": gate["decision"],
            "route_pack_status": gate["route_pack_status"],
            "selected_skill_name": gate["selected_skill"]["name"],
            "selected_graph_id": gate["graph_targets"]["selected_graph_id"],
            "graph_context_ids": gate["graph_targets"]["graph_context_ids"],
            "blocking_hazard_codes": gate["blocking_hazard_codes"],
            "clarification_hazard_codes": gate["clarification_hazard_codes"],
            "preflight_status": gate["freshness_and_evidence"]["preflight_status"],
            "allowed_federation_tools": gate["allowed_tools"]["federation_mcp_tools"],
            "allowed_graph_local_tools": gate["allowed_tools"][
                "graph_local_mcp_tools_after_selection"
            ],
            "required_verification_commands": [
                command["command"] for command in gate["required_verification_commands"]
            ],
        }
    mismatches = [
        {"field": field, "expected": expected, "actual": actual.get(field)}
        for field, expected in case["expected"].items()
        if actual.get(field) != expected
    ]
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "mode": case["mode"],
        "status": "failed" if mismatches else "passed",
        "expected": case["expected"],
        "actual": actual,
        "mismatches": mismatches,
    }


def _routing_eval_preflight(registry: RtgGraphRegistry) -> dict[str, Any]:
    graphs = [
        {"graph_id": graph.graph_id, "status": "ready"}
        for graph in registry.list_graphs().graphs
    ]
    return {
        "status": "passed",
        "graph_count": len(graphs),
        "ready_graph_count": len(graphs),
        "skipped_graph_count": 0,
        "not_ready_graph_count": 0,
        "not_ready_graph_ids": [],
        "graphs": graphs,
        "evidence_scope": "deterministic routing evaluation; runtime preflight is separate",
    }


def _required_str(payload: dict[str, object], key: str, *, index: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RtgFederationEvalInvalid(
            f"routing matrix case {index} {key} must be a non-empty string"
        )
    return value.strip()


def _optional_str(payload: dict[str, object], key: str, *, case_id: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RtgFederationEvalInvalid(
            f"routing matrix case {case_id} intent.{key} must be a non-empty string"
        )
    return value.strip()


def _str_list(payload: dict[str, object], key: str, *, case_id: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise RtgFederationEvalInvalid(
            f"routing matrix case {case_id} intent.{key} must be a list of non-empty strings"
        )
    return [item.strip() for item in value]


if __name__ == "__main__":
    raise SystemExit(main())
