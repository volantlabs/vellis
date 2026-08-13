from __future__ import annotations

import copy

from tools import system_evolution


def _record() -> dict[str, object]:
    return system_evolution.load_record()


def test_committed_evolution_record_is_valid() -> None:
    assert system_evolution.validate_record(_record()) == []


def test_unknown_owned_finding_is_rejected() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][0]["finding_ids"].append("F999")  # type: ignore[index,union-attr]
    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]
    assert any("owns unknown finding F999" in finding for finding in findings)


def test_pending_approval_cannot_enter_execution() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][0]["lifecycle"] = "active"  # type: ignore[index]
    record["work_items"][0]["approval"]["status"] = "pending"  # type: ignore[index]
    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]
    assert any("unsatisfied approval" in finding for finding in findings)


def test_only_one_work_item_may_be_active() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][0]["lifecycle"] = "active"  # type: ignore[index]
    record["work_items"][1]["lifecycle"] = "active"  # type: ignore[index]
    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]
    assert "more than one work item is active" in findings


def test_current_baseline_must_match_the_observed_target() -> None:
    record = copy.deepcopy(_record())
    record["baselines"]["observed"]["implementation"] = "different"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "current baselines must match the observed target or source baseline" in findings


def test_resolved_findings_and_conforming_decisions_require_evidence() -> None:
    record = copy.deepcopy(_record())
    record["findings"][0]["disposition"] = "resolved"  # type: ignore[index]
    record["findings"][0]["implementation_status"] = "conforming"  # type: ignore[index]
    record["findings"][0]["evidence_refs"] = []  # type: ignore[index]
    record["decisions"][0]["implementation_status"] = "conforming"  # type: ignore[index]
    record["decisions"][0]["evidence_refs"] = []  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "resolved finding F001 has no evidence" in findings
    assert "conforming decision D001 has no evidence" in findings


def test_complete_work_item_cannot_retain_open_owned_work() -> None:
    record = copy.deepcopy(_record())
    item = record["work_items"][1]  # type: ignore[index]
    item["lifecycle"] = "complete"
    item["implementation_status"] = "conforming"
    item["checkpoint"] = "git:checkpoint"

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "complete work item W002 has open findings ['F002', 'F003']" in findings


def test_status_reports_the_active_item_before_another_ready_item() -> None:
    report = system_evolution.status(_record())  # type: ignore[arg-type]

    assert "next_work: W003" in report


def test_ready_work_requires_complete_dependencies() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][3]["lifecycle"] = "ready"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("ready work item W004 has incomplete dependencies" in each for each in findings)


def test_accepted_approval_requires_an_attributable_checkpoint() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][2]["approval"]["checkpoint"] = None  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "accepted approval for W003 has no attributable checkpoint" in findings


def test_unknown_blocker_finding_and_duplicate_ownership_are_rejected() -> None:
    record = copy.deepcopy(_record())
    record["evolution"]["lifecycle"] = "blocked"  # type: ignore[index]
    record["evolution"]["blocker"] = {  # type: ignore[index]
        "classification": "external dependency",
        "summary": "A bounded external dependency is unavailable.",
        "finding_ids": ["F999"],
        "evidence_refs": [],
    }
    record["work_items"][1]["lifecycle"] = "blocked"  # type: ignore[index]
    record["work_items"][1]["blocker"] = {  # type: ignore[index]
        "classification": "external dependency",
        "summary": "The same bounded dependency blocks this work item.",
        "finding_ids": ["F002"],
        "evidence_refs": [],
    }
    record["work_items"][0]["finding_ids"].append("F002")  # type: ignore[index,union-attr]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "evolution blocker names unknown finding F999" in findings
    assert any("finding F002 is listed by" in finding for finding in findings)
