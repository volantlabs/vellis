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
    record["findings"][1]["disposition"] = "implementation-work"  # type: ignore[index]
    record["findings"][1]["implementation_status"] = "partial"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "complete work item W002 has open findings ['F002']" in findings


def test_status_reports_the_active_item_before_another_ready_item() -> None:
    report = system_evolution.status(_record())  # type: ignore[arg-type]

    assert "next_work: W004" in report


def test_ready_work_requires_complete_dependencies() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][2]["lifecycle"] = "pending"  # type: ignore[index]
    record["work_items"][3]["lifecycle"] = "ready"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("ready work item W004 has incomplete dependencies" in each for each in findings)


def test_accepted_approval_requires_an_attributable_checkpoint() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][2]["approval"]["checkpoint"] = None  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "accepted approval for W003 has no attributable checkpoint" in findings


def test_active_work_cannot_remain_bound_only_to_a_source_baseline() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][3]["planned_baseline"] = record["baselines"]["source"]["implementation"]  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("active work item W004 has stale planned baseline" in each for each in findings)


def test_complete_work_requires_complete_dependencies() -> None:
    record = copy.deepcopy(_record())
    record["work_items"][1]["lifecycle"] = "pending"  # type: ignore[index]
    record["work_items"][3]["lifecycle"] = "complete"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("complete work item W004 has incomplete dependencies" in each for each in findings)


def test_complete_closure_requires_named_evidenced_review_lenses() -> None:
    record = copy.deepcopy(_record())
    for item in record["work_items"]:  # type: ignore[union-attr]
        item["lifecycle"] = "complete"
        item["implementation_status"] = "conforming"
        item["checkpoint"] = "git:complete"
    record["evolution"]["lifecycle"] = "complete"  # type: ignore[index]
    record["evolution"]["checkpoint"] = "git:complete"  # type: ignore[index]
    record["baselines"]["target"]["checkpoint"] = "git:complete"  # type: ignore[index]
    record["baselines"]["observed"]["checkpoint"] = "git:complete"  # type: ignore[index]
    closure = record["closure"]  # type: ignore[index]
    closure.update(  # type: ignore[union-attr]
        finding_disposition="complete",
        model_status="accepted",
        implementation_status="conforming",
        integration_status="conforming",
        external_status="not applicable",
        checkpoint="git:complete",
        evidence_refs=["command:just check"],
        reviews=[
            {"lens": "foo", "status": "clean", "evidence_refs": []},
            {"lens": "bar", "status": "clean", "evidence_refs": []},
        ],
    )

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("lacks clean required review lenses" in each for each in findings)


def test_git_checkpoints_must_resolve_to_commits() -> None:
    record = copy.deepcopy(_record())
    record["baselines"]["source"]["checkpoint"] = "git:does-not-exist"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "Git checkpoint does not resolve to a commit: git:does-not-exist" in findings


def test_complete_closure_rejects_duplicate_or_unresolved_reviews() -> None:
    record = copy.deepcopy(_record())
    for item in record["work_items"]:  # type: ignore[union-attr]
        item["lifecycle"] = "complete"
        item["implementation_status"] = "conforming"
        item["checkpoint"] = "git:ee86d59"
    record["evolution"]["lifecycle"] = "complete"  # type: ignore[index]
    record["evolution"]["checkpoint"] = "git:ee86d59"  # type: ignore[index]
    record["baselines"]["target"]["checkpoint"] = "git:ee86d59"  # type: ignore[index]
    record["baselines"]["observed"]["checkpoint"] = "git:ee86d59"  # type: ignore[index]
    closure = record["closure"]  # type: ignore[index]
    closure.update(  # type: ignore[union-attr]
        finding_disposition="complete",
        model_status="accepted",
        implementation_status="conforming",
        integration_status="conforming",
        external_status="not applicable",
        checkpoint="git:ee86d59",
        evidence_refs=["command:just check"],
        reviews=[
            {
                "lens": "authority and conformance",
                "status": "clean",
                "evidence_refs": ["command:just model-check"],
            },
            {
                "lens": "engineering and evidence",
                "status": "findings",
                "evidence_refs": [],
            },
            {
                "lens": "engineering and evidence",
                "status": "clean",
                "evidence_refs": ["command:just check"],
            },
        ],
    )

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("duplicate review lenses" in each for each in findings)
    assert any("unresolved reviews" in each for each in findings)


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
