from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools import rtg_federation_workload_eval as workload_eval
from tools.rtg_federation_workload_eval import (
    DEFAULT_CASES_PATH,
    RtgFederationWorkloadEvalInvalid,
    evaluate_workload_matrix,
    main,
)


def test_default_workload_matrix_schema_is_valid() -> None:
    matrix = workload_eval._load_matrix(DEFAULT_CASES_PATH)

    assert matrix["version"] == 1
    assert [case["case_id"] for case in matrix["cases"]] == [
        "three_graph_execution_and_citations",
        "temporal_personal_and_repo_read",
        "experience_publication_readiness",
        "grounded_cross_graph_comparison",
        "grounded_inference_with_uncertainty",
        "confirmed_repo_personal_bridge",
    ]


def test_workload_matrix_scores_runtime_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path, bridge_path, cases_path = _write_fixture_files(tmp_path)
    _install_runtime_fakes(monkeypatch)

    result = evaluate_workload_matrix(
        registry_path=registry_path,
        bridge_path=bridge_path,
        cases_path=cases_path,
    )

    assert result["status"] == "passed"
    assert result["case_count"] == 2
    assert result["passed_case_count"] == 2
    assert result["scorecard"]["overall"]["score"] == 1.0
    assert result["scorecard"]["dimensions"]["citation_resolution"]["score"] == 1.0
    assert result["scorecard"]["dimensions"]["bridge_traversal"]["score"] == 1.0
    assert result["cases"][0]["actual"]["resolved_citation_graph_ids"] == ["repo_twin"]
    assert result["cases"][1]["actual"]["source_resolution_status"] == "resolved"


def test_workload_matrix_reports_answer_contract_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path, bridge_path, cases_path = _write_fixture_files(tmp_path)
    _install_runtime_fakes(monkeypatch, answer_status="needs_attention")

    result = evaluate_workload_matrix(
        registry_path=registry_path,
        bridge_path=bridge_path,
        cases_path=cases_path,
    )

    assert result["status"] == "failed"
    assert result["failed_case_ids"] == ["repo_read"]
    mismatch = [
        check
        for check in result["cases"][0]["checks"]
        if check["name"] == "section_answers.repo_twin.status"
    ]
    assert mismatch == [
        {
            "dimension": "answer_usefulness",
            "name": "section_answers.repo_twin.status",
            "passed": False,
            "expected": "summarized",
            "actual": "needs_attention",
        }
    ]
    assert result["scorecard"]["dimensions"]["answer_usefulness"]["score"] < 1.0


def test_workload_matrix_rejects_duplicate_and_unknown_cases(tmp_path: Path) -> None:
    registry_path, bridge_path, cases_path = _write_fixture_files(tmp_path)
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]
    cases_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RtgFederationWorkloadEvalInvalid, match="duplicate workload matrix"):
        evaluate_workload_matrix(
            registry_path=registry_path,
            bridge_path=bridge_path,
            cases_path=cases_path,
        )

    payload["cases"] = [payload["cases"][0]]
    payload["cases"][0]["expected"]["unknown"] = True
    cases_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RtgFederationWorkloadEvalInvalid, match="unsupported expected fields"):
        evaluate_workload_matrix(
            registry_path=registry_path,
            bridge_path=bridge_path,
            cases_path=cases_path,
        )


def test_workload_eval_cli_prints_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path, bridge_path, cases_path = _write_fixture_files(tmp_path)
    _install_runtime_fakes(monkeypatch)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "--bridges",
            str(bridge_path),
            "--cases",
            str(cases_path),
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["scorecard"]["overall"]["score"] == 1.0


def _install_runtime_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    answer_status: str = "summarized",
) -> None:
    monkeypatch.setattr(
        workload_eval,
        "federated_preflight_payload",
        lambda registry: {"status": "passed"},
    )

    def fake_answer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = (args, kwargs)
        return {
            "status": "complete",
            "plan": {"steps": ({"graph_id": "repo_twin"},)},
            "join_execution": "not_performed",
            "write_execution": "not_performed",
            "synthesis": {
                "reads": (
                    {
                        "graph_id": "repo_twin",
                        "status": "executed",
                        "summary": {
                            "answer": {
                                "status": answer_status,
                                "component_count": 2,
                            }
                        },
                    },
                ),
                "citations": (
                    {
                        "graph_id": "repo_twin",
                        "local_uuid": "11111111-1111-4111-8111-111111111111",
                    },
                ),
                "limitations": (),
            },
        }

    monkeypatch.setattr(workload_eval, "federated_answer_payload", fake_answer)
    monkeypatch.setattr(
        workload_eval,
        "citation_resolution_payload",
        lambda *args, **kwargs: {"status": "resolved", "records": ({"row": 1},)},
    )
    monkeypatch.setattr(
        workload_eval,
        "bridge_traversal_payload",
        lambda *args, **kwargs: {
            "status": "resolved",
            "source": {"resolution": {"status": "resolved"}},
            "target": {"resolution": {"status": "resolved"}},
            "join_execution": "not_performed",
        },
    )


def _write_fixture_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    cases_path = tmp_path / "cases.json"
    registry_path.write_text(
        json.dumps(
            {
                "graphs": [
                    _graph("repo_twin", tmp_path / "repo", "derived_from_repo", "sync_only"),
                    _graph(
                        "personal_ops",
                        tmp_path / "personal",
                        "user_authored",
                        "explicit_target_required",
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )
    bridge_path.write_text(
        json.dumps(
            {
                "bridges": [
                    {
                        "bridge_type": "related_context",
                        "source": {
                            "graph_id": "repo_twin",
                            "local_uuid": "11111111-1111-4111-8111-111111111111",
                        },
                        "target": {
                            "graph_id": "personal_ops",
                            "local_uuid": "22222222-2222-4222-8222-222222222222",
                        },
                        "confidence": 0.8,
                        "asserted_at": "2026-07-10T00:00:00Z",
                        "asserted_by": "test",
                        "provenance": [
                            {
                                "graph_id": "repo_twin",
                                "local_uuid": "11111111-1111-4111-8111-111111111111",
                            }
                        ],
                    }
                ],
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )
    cases_path.write_text(json.dumps(_cases_payload()), encoding="utf-8")
    return registry_path, bridge_path, cases_path


def _graph(graph_id: str, root: Path, authority: str, write_policy: str) -> dict[str, Any]:
    return {
        "graph_id": graph_id,
        "title": graph_id,
        "storage_root": str(root),
        "sql_database_path": str(root / "controller.sqlite"),
        "authority": authority,
        "write_policy": write_policy,
        "domains": ["evidence"],
        "tags": [graph_id],
        "metadata": {},
    }


def _cases_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "cases": [
            {
                "case_id": "repo_read",
                "category": "read",
                "mode": "federated_answer",
                "intent": {"text": "Read repo evidence."},
                "expected": {
                    "status": "complete",
                    "planned_graph_ids": ["repo_twin"],
                    "executed_graph_ids": ["repo_twin"],
                    "max_limitation_count": 0,
                    "min_citation_count": 1,
                    "resolved_citation_graph_ids": ["repo_twin"],
                    "section_answers": {"repo_twin": {"status": "summarized"}},
                    "section_required_fields": {"repo_twin": ["component_count"]},
                    "join_execution": "not_performed",
                    "write_execution": "not_performed",
                },
            },
            {
                "case_id": "bridge",
                "category": "bridge",
                "mode": "bridge_traversal",
                "bridge_selector": {
                    "source_graph_id": "repo_twin",
                    "target_graph_id": "personal_ops",
                    "bridge_type": "related_context",
                },
                "expected": {
                    "status": "resolved",
                    "source_resolution_status": "resolved",
                    "target_resolution_status": "resolved",
                    "join_execution": "not_performed",
                },
            },
        ],
    }
