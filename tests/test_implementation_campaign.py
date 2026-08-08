from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest
import yaml

from tools import implementation_campaign, model_layout


def _campaign() -> dict[str, object]:
    return implementation_campaign.load_campaign(model_layout.IMPLEMENTATION_CAMPAIGN_PATH)


def test_committed_campaign_is_current_and_valid() -> None:
    campaign = _campaign()

    assert implementation_campaign.validate_campaign(campaign) == []
    assert (
        campaign["model_baseline"]["observed"]["authority_sha256"]  # type: ignore[index]
        == implementation_campaign.authority_digest()
    )


def test_duplicate_yaml_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "campaign.yaml"
    path.write_text('schema_version: "1.0"\nschema_version: "1.0"\n', encoding="utf-8")

    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key"):
        implementation_campaign.load_campaign(path)


def test_schema_rejects_unknown_fields() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["shadow_specification"] = {}  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("Additional properties are not allowed" in finding for finding in findings)


def test_schema_rejects_malformed_lifecycle_status() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "running"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("campaign.lifecycle" in finding and "running" in finding for finding in findings)


def test_unapproved_campaign_cannot_enter_execution() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "ready"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("unapproved plans" in finding for finding in findings)
    assert any("unapproved campaign" in finding for finding in findings)


def test_dependencies_must_exist_precede_and_remain_acyclic() -> None:
    campaign = copy.deepcopy(_campaign())
    first = campaign["slices"][0]  # type: ignore[index]
    second = campaign["slices"][1]  # type: ignore[index]
    first["dependencies"] = [second["id"]]
    second["dependencies"] = [first["id"], "S999"]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("unknown dependency S999" in finding for finding in findings)
    assert any("must have a lower order" in finding for finding in findings)
    assert any("dependency cycle" in finding for finding in findings)


def test_authority_and_slice_links_must_be_bidirectional() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["authority"][0]["slice_ids"].pop()  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("slice links are not bidirectional" in finding for finding in findings)


def test_only_one_slice_may_be_active() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": "approval:1",
    }
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "active"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("at most one slice may be active" in finding for finding in findings)


def test_interrupted_active_slice_is_a_valid_resumable_checkpoint() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": "approval:1",
    }
    campaign["campaign"]["checkpoint"] = "slice:S001:active"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]

    assert implementation_campaign.validate_campaign(campaign) == []
    assert "Active: S001 " in implementation_campaign._status(campaign)


def test_code_defect_cannot_masquerade_as_a_human_blocker() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "blocked"  # type: ignore[index]
    campaign["campaign"]["plan_approval"]["status"] = "changes-required"  # type: ignore[index]
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "implementation defect",
        "summary": "A bounded implementation defect must be remediated autonomously.",
        "authority_ids": [],
        "evidence_refs": [],
    }

    findings = implementation_campaign.validate_campaign(campaign)
    assert any("campaign.blocker" in finding and "is not valid" in finding for finding in findings)

    campaign["campaign"]["blocker"]["classification"] = "model gap"  # type: ignore[index]
    assert implementation_campaign.validate_campaign(campaign) == []


def test_joint_authority_contributions_remain_partial_until_aggregate_closure() -> None:
    campaign = copy.deepcopy(_campaign())
    joint_authority = next(entry for entry in campaign["authority"] if len(entry["slice_ids"]) > 1)  # type: ignore[index]
    contributor_id = joint_authority["slice_ids"][0]
    contributor = next(entry for entry in campaign["slices"] if entry["id"] == contributor_id)  # type: ignore[index]
    contribution = next(
        entry
        for entry in contributor["authority"]
        if entry["authority_id"] == joint_authority["id"]
    )
    contribution["coverage"] = "full"
    contribution["remaining_slice_ids"] = []

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must be self-sufficient" in finding for finding in findings)


def test_complete_slice_requires_conformance_evidence_and_checkpoint() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": "approval:1",
    }
    first = campaign["slices"][0]  # type: ignore[index]
    first["lifecycle"] = "complete"
    first["implementation_status"] = "partial"

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must be conforming" in finding for finding in findings)
    assert any("requires evidence" in finding for finding in findings)
    assert any("requires a checkpoint" in finding for finding in findings)


def test_campaign_completion_requires_full_system_closure() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "complete"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": "approval:1",
    }
    campaign["authority"][0]["planned_coverage"] = "partial"  # type: ignore[index]
    campaign["closure"]["authority_coverage"] = "partial"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("campaign requires every slice complete" in finding for finding in findings)
    assert any("requires every authority entry conforming" in finding for finding in findings)
    assert any("requires full aggregate authority coverage" in finding for finding in findings)
    assert any("requires conforming integration status" in finding for finding in findings)
    assert any("requires a conforming runnable boundary" in finding for finding in findings)
    assert any("requires closure evidence" in finding for finding in findings)
    assert any("requires a closure checkpoint" in finding for finding in findings)


def test_stale_baseline_blocks_execution_until_replanned(tmp_path: Path) -> None:
    shutil.copytree(model_layout.MODEL_ROOT, tmp_path / "model")
    language_lock = tmp_path / "model" / "config" / "language.lock.json"
    language_lock.write_text(language_lock.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    campaign = copy.deepcopy(_campaign())
    campaign["model_baseline"]["status"] = "stale"  # type: ignore[index]
    campaign["model_baseline"]["observed"].update(  # type: ignore[index]
        implementation_campaign.observed_baseline(tmp_path)
    )
    campaign["campaign"]["lifecycle"] = "stale"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "changes-required",
        "checkpoint": None,
    }
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "stale baseline",
        "summary": "The observed model or language baseline changed.",
        "authority_ids": [],
        "evidence_refs": [],
    }

    assert implementation_campaign.validate_campaign(campaign, root=tmp_path) == []

    campaign["model_baseline"]["planned"].update(  # type: ignore[index]
        implementation_campaign.observed_baseline(tmp_path)
    )
    campaign["model_baseline"]["status"] = "current"  # type: ignore[index]
    campaign["campaign"]["lifecycle"] = "awaiting-plan-approval"  # type: ignore[index]
    campaign["campaign"]["plan_approval"]["status"] = "pending"  # type: ignore[index]
    campaign["campaign"]["blocker"] = None  # type: ignore[index]

    assert implementation_campaign.validate_campaign(campaign, root=tmp_path) == []


def test_status_is_compact_and_deterministic() -> None:
    status = implementation_campaign._status(_campaign())

    assert status.splitlines() == [
        "Campaign: vellis-model-implementation",
        "Lifecycle: awaiting-plan-approval",
        "Baseline: current",
        "Plan approval: pending",
        "Slices: pending=17",
        "Active: none",
        "Next: none",
        "Blocker: none",
        "Closure: authority=full, integration=absent, runnable=absent",
        "Checkpoint: none",
    ]
