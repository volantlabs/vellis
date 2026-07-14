from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apps.rtg_federation.registry_io import (
    DEFAULT_REGISTRY_PATH,
    bridge_traversal_payload,
    citation_resolution_payload,
    default_bridge_path_for_registry,
    federated_answer_payload,
    federated_preflight_payload,
    federated_semantic_answer_payload,
    load_bridge_store,
    load_registry,
)
from components.rtg.controller import RtgControllerError
from components.rtg.evidence_bounded_synthesis import (
    RtgEvidenceBoundedSynthesisRequest,
    RtgEvidenceCitationRef,
    RtgSemanticClaimDraft,
    RtgSemanticSynthesisDraft,
)
from components.rtg.graph_bridge import RtgGraphBridge, RtgGraphBridgeError
from components.rtg.graph_registry import RtgGraphRegistry, RtgGraphRegistryError
from components.storage.json_file import StorageError
from components.storage.sql import SqlStorageError

DEFAULT_CASES_PATH = Path("docs/guides/vellis/evals/rtg-federation-workload-cases.json")
DIMENSIONS = (
    "execution_coverage",
    "limitations",
    "citation_resolution",
    "bridge_traversal",
    "temporal_scope",
    "answer_usefulness",
    "claim_grounding",
    "boundary_safety",
)
SUPPORTED_MODES = {
    "federated_answer",
    "evidence_bounded_synthesis",
    "bridge_traversal",
}
ANSWER_EXPECTED_FIELDS = {
    "status",
    "planned_graph_ids",
    "executed_graph_ids",
    "max_limitation_count",
    "min_citation_count",
    "resolved_citation_graph_ids",
    "section_answers",
    "section_required_fields",
    "join_execution",
    "write_execution",
}
BRIDGE_EXPECTED_FIELDS = {
    "status",
    "source_resolution_status",
    "target_resolution_status",
    "join_execution",
}
SEMANTIC_EXPECTED_FIELDS = {
    "status",
    "deterministic_status",
    "model_execution",
    "min_claim_count",
    "claim_kinds",
    "claim_citation_graph_ids",
    "entailment_status",
    "join_execution",
    "write_execution",
}


class RtgFederationWorkloadEvalInvalid(ValueError):
    """A federation workload matrix is malformed."""


def evaluate_workload_matrix(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cases_path: Path = DEFAULT_CASES_PATH,
    bridge_path: Path | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    resolved_bridge_path = bridge_path or default_bridge_path_for_registry(registry_path)
    bridge_store = load_bridge_store(resolved_bridge_path)
    matrix = _load_matrix(cases_path)
    preflight = federated_preflight_payload(registry)
    global_checks = [
        _check(
            dimension="execution_coverage",
            name="federation_preflight",
            expected="passed",
            actual=preflight.get("status"),
        )
    ]
    cases = [_evaluate_case(registry, bridge_store, case) for case in matrix["cases"]]
    failed_case_ids = [case["case_id"] for case in cases if case["status"] == "failed"]
    all_checks = global_checks + [check for case in cases for check in case["checks"]]
    scorecard = _scorecard(all_checks)
    status = (
        "passed"
        if not failed_case_ids and all(check["passed"] for check in global_checks)
        else "failed"
    )
    return {
        "status": status,
        "matrix_version": matrix["version"],
        "registry_path": str(registry_path),
        "bridge_path": str(resolved_bridge_path),
        "cases_path": str(cases_path),
        "preflight_status": preflight.get("status"),
        "case_count": len(cases),
        "passed_case_count": len(cases) - len(failed_case_ids),
        "failed_case_count": len(failed_case_ids),
        "failed_case_ids": failed_case_ids,
        "global_checks": global_checks,
        "scorecard": scorecard,
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rtg_federation_workload_eval")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--bridges", type=Path)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = evaluate_workload_matrix(
            registry_path=args.registry,
            cases_path=args.cases,
            bridge_path=args.bridges,
        )
    except (
        OSError,
        json.JSONDecodeError,
        RtgControllerError,
        RtgGraphBridgeError,
        RtgGraphRegistryError,
        RtgFederationWorkloadEvalInvalid,
        SqlStorageError,
        StorageError,
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
        overall = result["scorecard"]["overall"]
        print(
            f"status={result['status']} cases={result['case_count']} "
            f"passed={result['passed_case_count']} failed={result['failed_case_count']} "
            f"score={overall['score']:.3f}"
        )
        print(f"preflight={result['preflight_status']}")
        for dimension in DIMENSIONS:
            score = result["scorecard"]["dimensions"][dimension]
            rendered = "not_exercised" if score["score"] is None else f"{score['score']:.3f}"
            print(
                f"- {dimension} score={rendered} "
                f"passed={score['passed_checks']}/{score['total_checks']}"
            )
        for case in result["cases"]:
            print(f"- {case['case_id']} mode={case['mode']} status={case['status']}")
            for check in case["checks"]:
                if not check["passed"]:
                    print(
                        f"  {check['name']}: expected={check['expected']!r} "
                        f"actual={check['actual']!r}"
                    )
    return 0 if result["status"] == "passed" else 1


def _load_matrix(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RtgFederationWorkloadEvalInvalid("workload matrix root must be an object")
    if payload.get("version") != 1:
        raise RtgFederationWorkloadEvalInvalid("workload matrix version must be 1")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RtgFederationWorkloadEvalInvalid("workload matrix cases must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        item = _normalize_case(case, index=index)
        if item["case_id"] in seen:
            raise RtgFederationWorkloadEvalInvalid(
                f"duplicate workload matrix case_id: {item['case_id']}"
            )
        seen.add(item["case_id"])
        normalized.append(item)
    return {"version": 1, "cases": normalized}


def _normalize_case(payload: object, *, index: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RtgFederationWorkloadEvalInvalid(f"workload matrix case {index} must be an object")
    case_id = _required_str(payload, "case_id", context=f"case {index}")
    category = _required_str(payload, "category", context=case_id)
    mode = _required_str(payload, "mode", context=case_id)
    if mode not in SUPPORTED_MODES:
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix case {case_id} mode must be one of {sorted(SUPPORTED_MODES)}"
        )
    expected = payload.get("expected")
    if not isinstance(expected, dict) or not expected:
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix case {case_id} expected must be a non-empty object"
        )
    _validate_expected(case_id, mode, expected)
    normalized = {
        "case_id": case_id,
        "category": category,
        "mode": mode,
        "expected": expected,
    }
    if mode in {"federated_answer", "evidence_bounded_synthesis"}:
        intent = payload.get("intent")
        if not isinstance(intent, dict):
            raise RtgFederationWorkloadEvalInvalid(
                f"workload matrix case {case_id} intent must be an object"
            )
        normalized["intent"] = {
            "text": _required_str(intent, "text", context=case_id),
            "target_graph_ids": _str_list(intent, "target_graph_ids", context=case_id),
            "domain_hints": _str_list(intent, "domain_hints", context=case_id),
            "tag_hints": _str_list(intent, "tag_hints", context=case_id),
        }
        if mode == "evidence_bounded_synthesis":
            normalized["draft"] = _normalize_semantic_draft(
                payload.get("draft"),
                context=case_id,
            )
    else:
        selector = payload.get("bridge_selector")
        if not isinstance(selector, dict):
            raise RtgFederationWorkloadEvalInvalid(
                f"workload matrix case {case_id} bridge_selector must be an object"
            )
        normalized["bridge_selector"] = {
            "source_graph_id": _required_str(selector, "source_graph_id", context=case_id),
            "target_graph_id": _required_str(selector, "target_graph_id", context=case_id),
            "bridge_type": _optional_str(selector, "bridge_type", context=case_id),
        }
    return normalized


def _evaluate_case(
    registry: RtgGraphRegistry,
    bridge_store: RtgGraphBridge,
    case: dict[str, Any],
) -> dict[str, Any]:
    try:
        if case["mode"] == "federated_answer":
            actual, checks = _evaluate_answer_case(registry, bridge_store, case)
        elif case["mode"] == "evidence_bounded_synthesis":
            actual, checks = _evaluate_semantic_case(registry, bridge_store, case)
        else:
            actual, checks = _evaluate_bridge_case(registry, bridge_store, case)
    except Exception as error:  # noqa: BLE001 - runtime failures are workload evidence
        actual = {"runtime_error": {"type": type(error).__name__, "message": str(error)}}
        checks = [
            _check(
                dimension="execution_coverage",
                name="runtime_error",
                expected=None,
                actual=actual["runtime_error"],
                passed=False,
            )
        ]
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "mode": case["mode"],
        "status": "passed" if all(check["passed"] for check in checks) else "failed",
        "actual": actual,
        "checks": checks,
    }


def _evaluate_answer_case(
    registry: RtgGraphRegistry,
    bridge_store: RtgGraphBridge,
    case: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    intent = case["intent"]
    payload = federated_answer_payload(
        registry,
        text=intent["text"],
        target_graph_ids=tuple(intent["target_graph_ids"]),
        domain_hints=tuple(intent["domain_hints"]),
        tag_hints=tuple(intent["tag_hints"]),
        bridge_store=bridge_store,
    )
    synthesis = payload.get("synthesis")
    synthesis = synthesis if isinstance(synthesis, dict) else {}
    plan = payload.get("plan")
    plan = plan if isinstance(plan, dict) else {}
    steps = plan.get("steps")
    steps = steps if isinstance(steps, list | tuple) else []
    reads = synthesis.get("reads")
    reads = reads if isinstance(reads, list | tuple) else []
    citations = synthesis.get("citations")
    citations = citations if isinstance(citations, list | tuple) else []
    limitations = synthesis.get("limitations")
    limitations = limitations if isinstance(limitations, list | tuple) else []
    answers = _answers_by_graph(reads)
    actual: dict[str, Any] = {
        "status": payload.get("status"),
        "planned_graph_ids": [step.get("graph_id") for step in steps if isinstance(step, dict)],
        "executed_graph_ids": [
            read.get("graph_id")
            for read in reads
            if isinstance(read, dict) and read.get("status") == "executed"
        ],
        "limitation_count": len(limitations),
        "citation_count": len(citations),
        "join_execution": payload.get("join_execution"),
        "write_execution": payload.get("write_execution"),
        "section_answers": answers,
    }
    expected = case["expected"]
    checks: list[dict[str, Any]] = []
    for field in ("status", "planned_graph_ids", "executed_graph_ids"):
        if field in expected:
            checks.append(_check("execution_coverage", field, expected[field], actual.get(field)))
    if "max_limitation_count" in expected:
        maximum = expected["max_limitation_count"]
        checks.append(
            _check(
                "limitations",
                "max_limitation_count",
                maximum,
                actual["limitation_count"],
                passed=isinstance(maximum, int) and actual["limitation_count"] <= maximum,
            )
        )
    if "min_citation_count" in expected:
        minimum = expected["min_citation_count"]
        checks.append(
            _check(
                "citation_resolution",
                "min_citation_count",
                minimum,
                actual["citation_count"],
                passed=isinstance(minimum, int) and actual["citation_count"] >= minimum,
            )
        )
    if "resolved_citation_graph_ids" in expected:
        requested = expected["resolved_citation_graph_ids"]
        resolved = _resolve_sample_citations(registry, citations, requested)
        actual["resolved_citation_graph_ids"] = resolved
        checks.append(
            _check("citation_resolution", "resolved_citation_graph_ids", requested, resolved)
        )
    for field in ("join_execution", "write_execution"):
        if field in expected:
            checks.append(_check("boundary_safety", field, expected[field], actual.get(field)))
    _append_section_checks(checks, answers, expected)
    return actual, checks


def _evaluate_bridge_case(
    registry: RtgGraphRegistry,
    bridge_store: RtgGraphBridge,
    case: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selector = case["bridge_selector"]
    bridges = [
        bridge
        for bridge in bridge_store.list_bridges(status="active").bridges
        if bridge.source.graph_id == selector["source_graph_id"]
        and bridge.target.graph_id == selector["target_graph_id"]
        and (selector["bridge_type"] is None or bridge.bridge_type == selector["bridge_type"])
    ]
    if len(bridges) != 1:
        actual = {"matching_bridge_count": len(bridges)}
        return actual, [
            _check(
                "bridge_traversal",
                "matching_bridge_count",
                1,
                len(bridges),
            )
        ]
    payload = bridge_traversal_payload(
        registry,
        bridge_store,
        bridge_id=bridges[0].bridge_id,
    )
    source = payload.get("source")
    source = source if isinstance(source, dict) else {}
    target = payload.get("target")
    target = target if isinstance(target, dict) else {}
    source_resolution = source.get("resolution")
    source_resolution = source_resolution if isinstance(source_resolution, dict) else {}
    target_resolution = target.get("resolution")
    target_resolution = target_resolution if isinstance(target_resolution, dict) else {}
    actual = {
        "bridge_id": bridges[0].bridge_id,
        "status": payload.get("status"),
        "source_resolution_status": source_resolution.get("status"),
        "target_resolution_status": target_resolution.get("status"),
        "join_execution": payload.get("join_execution"),
    }
    expected = case["expected"]
    checks = [
        _check("bridge_traversal", field, expected[field], actual.get(field))
        for field in ("status", "source_resolution_status", "target_resolution_status")
        if field in expected
    ]
    if "join_execution" in expected:
        checks.append(
            _check(
                "boundary_safety",
                "join_execution",
                expected["join_execution"],
                actual["join_execution"],
            )
        )
    return actual, checks


def _evaluate_semantic_case(
    registry: RtgGraphRegistry,
    bridge_store: RtgGraphBridge,
    case: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    intent = case["intent"]
    payload = federated_semantic_answer_payload(
        registry,
        text=intent["text"],
        target_graph_ids=tuple(intent["target_graph_ids"]),
        domain_hints=tuple(intent["domain_hints"]),
        tag_hints=tuple(intent["tag_hints"]),
        bridge_store=bridge_store,
        semantic_generator=_FixtureSemanticGenerator(case["draft"]),
    )
    semantic = payload.get("semantic_synthesis")
    semantic = semantic if isinstance(semantic, dict) else {}
    deterministic = payload.get("deterministic_answer")
    deterministic = deterministic if isinstance(deterministic, dict) else {}
    claims = semantic.get("claims")
    claims = claims if isinstance(claims, list | tuple) else []
    citation_graph_id_set: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_citations = claim.get("citations")
        if not isinstance(claim_citations, list | tuple):
            continue
        for citation in claim_citations:
            if not isinstance(citation, dict):
                continue
            graph_id = citation.get("graph_id")
            if isinstance(graph_id, str):
                citation_graph_id_set.add(graph_id)
    citation_graph_ids = sorted(citation_graph_id_set)
    actual = {
        "status": payload.get("status"),
        "deterministic_status": deterministic.get("status"),
        "model_execution": payload.get("model_execution"),
        "claim_count": len(claims),
        "claim_kinds": [claim.get("kind") for claim in claims if isinstance(claim, dict)],
        "claim_citation_graph_ids": citation_graph_ids,
        "entailment_status": semantic.get("entailment_status"),
        "join_execution": payload.get("join_execution"),
        "write_execution": payload.get("write_execution"),
    }
    expected = case["expected"]
    checks: list[dict[str, Any]] = []
    for field in ("status", "deterministic_status", "model_execution"):
        if field in expected:
            checks.append(_check("execution_coverage", field, expected[field], actual.get(field)))
    if "min_claim_count" in expected:
        minimum = expected["min_claim_count"]
        checks.append(
            _check(
                "claim_grounding",
                "min_claim_count",
                minimum,
                actual["claim_count"],
                passed=isinstance(minimum, int) and actual["claim_count"] >= minimum,
            )
        )
    for field in ("claim_kinds", "claim_citation_graph_ids", "entailment_status"):
        if field in expected:
            checks.append(_check("claim_grounding", field, expected[field], actual.get(field)))
    for field in ("join_execution", "write_execution"):
        if field in expected:
            checks.append(_check("boundary_safety", field, expected[field], actual.get(field)))
    return actual, checks


def _resolve_sample_citations(
    registry: RtgGraphRegistry,
    citations: list[Any] | tuple[Any, ...],
    graph_ids: object,
) -> list[str]:
    if not isinstance(graph_ids, list) or not all(isinstance(item, str) for item in graph_ids):
        return []
    resolved: list[str] = []
    for graph_id in graph_ids:
        citation = next(
            (
                item
                for item in citations
                if isinstance(item, dict)
                and item.get("graph_id") == graph_id
                and isinstance(item.get("local_uuid"), str)
            ),
            None,
        )
        if citation is None:
            continue
        result = citation_resolution_payload(
            registry,
            graph_id=graph_id,
            local_uuid=citation["local_uuid"],
        )
        records = result.get("records")
        if result.get("status") == "resolved" and isinstance(records, list | tuple) and records:
            resolved.append(graph_id)
    return resolved


def _answers_by_graph(reads: list[Any] | tuple[Any, ...]) -> dict[str, dict[str, Any]]:
    answers: dict[str, dict[str, Any]] = {}
    for read in reads:
        if not isinstance(read, dict) or read.get("status") != "executed":
            continue
        graph_id = read.get("graph_id")
        summary = read.get("summary")
        if not isinstance(graph_id, str) or not isinstance(summary, dict):
            continue
        answer = summary.get("answer")
        if isinstance(answer, dict):
            answers[graph_id] = answer
    return answers


def _append_section_checks(
    checks: list[dict[str, Any]],
    answers: dict[str, dict[str, Any]],
    expected: dict[str, Any],
) -> None:
    section_answers = expected.get("section_answers", {})
    if isinstance(section_answers, dict):
        for graph_id, fields in section_answers.items():
            if not isinstance(graph_id, str) or not isinstance(fields, dict):
                continue
            answer = answers.get(graph_id, {})
            for field, value in fields.items():
                dimension = (
                    "temporal_scope"
                    if field in {"attention_scope", "attention_window"}
                    else "answer_usefulness"
                )
                checks.append(
                    _check(
                        dimension,
                        f"section_answers.{graph_id}.{field}",
                        value,
                        answer.get(field),
                    )
                )
    required = expected.get("section_required_fields", {})
    if isinstance(required, dict):
        for graph_id, fields in required.items():
            answer = answers.get(graph_id, {})
            if not isinstance(graph_id, str) or not isinstance(fields, list):
                continue
            for field in fields:
                if not isinstance(field, str):
                    continue
                checks.append(
                    _check(
                        "answer_usefulness",
                        f"section_required_fields.{graph_id}.{field}",
                        "present",
                        "present" if field in answer else "missing",
                    )
                )


class _FixtureSemanticGenerator:
    def __init__(self, draft: dict[str, Any]) -> None:
        self._draft = draft

    def generate(
        self,
        request: RtgEvidenceBoundedSynthesisRequest,
    ) -> RtgSemanticSynthesisDraft:
        citations_by_graph = {citation.graph_id: citation for citation in request.source.citations}
        claims: list[RtgSemanticClaimDraft] = []
        for claim in self._draft["claims"]:
            references: list[RtgEvidenceCitationRef] = []
            for graph_id in claim["citation_graph_ids"]:
                citation = citations_by_graph.get(graph_id)
                if citation is None:
                    raise RtgFederationWorkloadEvalInvalid(
                        f"semantic fixture references graph without source evidence: {graph_id}"
                    )
                references.append(
                    RtgEvidenceCitationRef(
                        graph_id=citation.graph_id,
                        local_uuid=citation.local_uuid,
                    )
                )
            claims.append(
                RtgSemanticClaimDraft(
                    text=claim["text"],
                    kind=claim["kind"],
                    citation_refs=tuple(references),
                    uncertainty=claim["uncertainty"],
                )
            )
        return RtgSemanticSynthesisDraft(
            claims=tuple(claims),
            limitations=tuple(self._draft["limitations"]),
        )


def _check(
    dimension: str,
    name: str,
    expected: Any,
    actual: Any,
    *,
    passed: bool | None = None,
) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "name": name,
        "passed": actual == expected if passed is None else passed,
        "expected": expected,
        "actual": actual,
    }


def _scorecard(checks: list[dict[str, Any]]) -> dict[str, Any]:
    dimensions: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        relevant = [check for check in checks if check["dimension"] == dimension]
        passed = sum(1 for check in relevant if check["passed"])
        dimensions[dimension] = {
            "passed_checks": passed,
            "total_checks": len(relevant),
            "score": passed / len(relevant) if relevant else None,
        }
    passed = sum(1 for check in checks if check["passed"])
    return {
        "overall": {
            "passed_checks": passed,
            "total_checks": len(checks),
            "score": passed / len(checks) if checks else 0.0,
        },
        "dimensions": dimensions,
    }


def _required_str(payload: dict[str, object], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix {context} {key} must be a non-empty string"
        )
    return value.strip()


def _optional_str(
    payload: dict[str, object],
    key: str,
    *,
    context: str,
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix {context} {key} must be a non-empty string"
        )
    return value.strip()


def _str_list(payload: dict[str, object], key: str, *, context: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix {context} {key} must be a list of non-empty strings"
        )
    return [item.strip() for item in value]


def _validate_expected(case_id: str, mode: str, expected: dict[str, Any]) -> None:
    if mode == "federated_answer":
        allowed = ANSWER_EXPECTED_FIELDS
    elif mode == "evidence_bounded_synthesis":
        allowed = SEMANTIC_EXPECTED_FIELDS
    else:
        allowed = BRIDGE_EXPECTED_FIELDS
    unknown = sorted(set(expected) - allowed)
    if unknown:
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix case {case_id} has unsupported expected fields: {', '.join(unknown)}"
        )
    if mode == "evidence_bounded_synthesis":
        for field in ("claim_kinds", "claim_citation_graph_ids"):
            if field in expected and not _is_str_list(expected[field]):
                raise RtgFederationWorkloadEvalInvalid(
                    f"workload matrix case {case_id} expected.{field} must be a list of strings"
                )
        minimum = expected.get("min_claim_count")
        if minimum is not None and (not isinstance(minimum, int) or minimum < 0):
            raise RtgFederationWorkloadEvalInvalid(
                f"workload matrix case {case_id} expected.min_claim_count must be a "
                "non-negative integer"
            )
        return
    if mode != "federated_answer":
        return
    for field in (
        "planned_graph_ids",
        "executed_graph_ids",
        "resolved_citation_graph_ids",
    ):
        if field in expected and not _is_str_list(expected[field]):
            raise RtgFederationWorkloadEvalInvalid(
                f"workload matrix case {case_id} expected.{field} must be a list of strings"
            )
    for field in ("max_limitation_count", "min_citation_count"):
        value = expected.get(field)
        if value is not None and (not isinstance(value, int) or value < 0):
            raise RtgFederationWorkloadEvalInvalid(
                f"workload matrix case {case_id} expected.{field} must be a non-negative integer"
            )
    section_answers = expected.get("section_answers")
    if section_answers is not None and (
        not isinstance(section_answers, dict)
        or not all(
            isinstance(graph_id, str) and isinstance(fields, dict)
            for graph_id, fields in section_answers.items()
        )
    ):
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix case {case_id} expected.section_answers must map graph ids to objects"
        )
    required = expected.get("section_required_fields")
    if required is not None and (
        not isinstance(required, dict)
        or not all(
            isinstance(graph_id, str) and _is_str_list(fields)
            for graph_id, fields in required.items()
        )
    ):
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix case {case_id} expected.section_required_fields must map graph ids "
            "to string lists"
        )


def _is_str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _normalize_semantic_draft(payload: object, *, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix case {context} draft must be an object"
        )
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list):
        raise RtgFederationWorkloadEvalInvalid(
            f"workload matrix case {context} draft.claims must be a list"
        )
    claims: list[dict[str, Any]] = []
    for index, claim in enumerate(raw_claims):
        if not isinstance(claim, dict):
            raise RtgFederationWorkloadEvalInvalid(
                f"workload matrix case {context} draft claim {index} must be an object"
            )
        claims.append(
            {
                "text": _required_str(claim, "text", context=f"{context} draft claim {index}"),
                "kind": _required_str(claim, "kind", context=f"{context} draft claim {index}"),
                "citation_graph_ids": _str_list(
                    claim,
                    "citation_graph_ids",
                    context=f"{context} draft claim {index}",
                ),
                "uncertainty": _optional_str(
                    claim,
                    "uncertainty",
                    context=f"{context} draft claim {index}",
                ),
            }
        )
    return {
        "claims": claims,
        "limitations": _str_list(payload, "limitations", context=f"{context} draft"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
