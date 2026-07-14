from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.rtg_federation_eval import (
    DEFAULT_CASES_PATH,
    RtgFederationEvalInvalid,
    evaluate_routing_matrix,
    main,
)


def test_default_federation_routing_matrix_passes() -> None:
    result = evaluate_routing_matrix()

    assert result["status"] == "passed"
    assert result["case_count"] == 22
    assert result["passed_case_count"] == 22
    assert result["failed_case_ids"] == []
    today = [case for case in result["cases"] if case["case_id"] == "personal_attention_today_read"]
    assert today[0]["actual"]["selected_graph_id"] == "personal_ops"
    experience = [
        case for case in result["cases"] if case["case_id"] == "experience_publication_readiness"
    ]
    assert experience[0]["actual"]["selected_graph_id"] == "experience_studio"
    portfolio = [
        case for case in result["cases"] if case["case_id"] == "application_portfolio_comparison"
    ]
    assert portfolio[0]["actual"]["selected_graph_id"] == "application_portfolio"
    route_pack = [
        case for case in result["cases"] if case["case_id"] == "three_graph_route_pack_preview"
    ]
    assert route_pack[0]["actual"]["selected_skill_name"] == "rtg-federation-control-plane"
    assert route_pack[0]["actual"]["graph_ids"] == [
        "personal_ops",
        "gothic_archive",
        "repo_twin",
    ]
    assert route_pack[0]["actual"]["preflight_status"] == "passed"
    assert "just graph-verify" in route_pack[0]["actual"]["verification_commands"]
    route_gate = [
        case for case in result["cases"] if case["case_id"] == "three_graph_route_pack_gate_invokes"
    ]
    assert route_gate[0]["actual"]["decision"] == "invoke"
    assert route_gate[0]["actual"]["selected_skill_name"] == "rtg-federation-control-plane"
    assert "vellis_route_pack_gate" in route_gate[0]["actual"]["allowed_federation_tools"]
    assert "rtg_validate_graph" in route_gate[0]["actual"]["allowed_graph_local_tools"]


def test_federation_routing_matrix_reports_field_mismatches(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["expected"]["selected_graph_id"] = "personal_ops"
    cases_path = tmp_path / "routing-cases.json"
    cases_path.write_text(json.dumps(payload), encoding="utf-8")

    result = evaluate_routing_matrix(cases_path=cases_path)

    assert result["status"] == "failed"
    assert result["failed_case_ids"] == ["repo_component_evidence_read"]
    assert result["cases"][0]["mismatches"] == [
        {
            "field": "selected_graph_id",
            "expected": "personal_ops",
            "actual": "repo_twin",
        }
    ]


def test_federation_routing_matrix_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8"))
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]
    cases_path = tmp_path / "routing-cases.json"
    cases_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RtgFederationEvalInvalid, match="duplicate routing matrix case_id"):
        evaluate_routing_matrix(cases_path=cases_path)


def test_federation_routing_eval_cli_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--json"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["case_count"] == 22
