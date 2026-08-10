from __future__ import annotations

import copy
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tools import implementation_campaign, model_layout, sysml_validator

PLAN_SHA = "1" * 40
APPROVAL_CHECKPOINT = f"approval:{PLAN_SHA}"
SUPERSEDED_PLAN_SHORT_SHA = "9" * 12


def _campaign() -> dict[str, object]:
    return implementation_campaign.load_campaign(model_layout.IMPLEMENTATION_CAMPAIGN_PATH)


def _approve(campaign: dict[str, object]) -> None:
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": APPROVAL_CHECKPOINT,
    }
    campaign["campaign"]["checkpoint"] = APPROVAL_CHECKPOINT  # type: ignore[index]


def _pending_campaign() -> dict[str, object]:
    """The committed plan reset to its pre-approval baseline.

    These tests exercise the checker's rules, not the campaign's own progress. Starting
    from a neutral baseline keeps them meaningful as slices are approved and completed,
    instead of freezing whichever lifecycle the live record happens to be in.
    """
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "awaiting-plan-approval"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {"status": "pending", "checkpoint": None}  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = None  # type: ignore[index]
    campaign["campaign"]["blocker"] = None  # type: ignore[index]
    for entry in campaign["authority"]:  # type: ignore[union-attr]
        entry["implementation_status"] = "absent"
        entry["evidence_refs"] = []
    for entry in campaign["slices"]:  # type: ignore[union-attr]
        entry["lifecycle"] = "pending"
        entry["implementation_status"] = "absent"
        entry["evidence_refs"] = []
        entry["blocker"] = None
        entry["checkpoint"] = None
    closure = campaign["closure"]
    closure["integration_status"] = "absent"  # type: ignore[index]
    closure["runnable_status"] = "absent"  # type: ignore[index]
    closure["evidence_refs"] = []  # type: ignore[index]
    closure["checkpoint"] = None  # type: ignore[index]
    return campaign


def _replanned_campaign() -> dict[str, object]:
    """A campaign whose first three slices completed under a superseded approved plan.

    Replanning after execution is the case a first approval cannot express. A corrected
    plan narrows what those slices claimed and moves the remainder into later slices, so
    the work they committed stays valid and keeps the label it earned.
    """
    campaign = _replanned_slices(_pending_campaign())
    return campaign


def _replanned_slices(campaign: dict[str, object]) -> dict[str, object]:
    for index in range(3):
        entry = campaign["slices"][index]  # type: ignore[index]
        entry["lifecycle"] = "complete"
        entry["implementation_status"] = "conforming"
        entry["evidence_refs"] = ["command:just check"]
        entry["checkpoint"] = f"slice:S00{index + 1}:{SUPERSEDED_PLAN_SHORT_SHA}:1"
    return campaign


def _renew(campaign: dict[str, object], *, checkpoint: str = APPROVAL_CHECKPOINT) -> None:
    """Grant the renewed approval: only the approval state and the next slice move."""
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": checkpoint,
    }
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    campaign["slices"][3]["lifecycle"] = "ready"  # type: ignore[index]


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write_campaign(root: Path, campaign: dict[str, object]) -> None:
    (root / "implementation-campaign.yaml").write_text(
        yaml.safe_dump(campaign, sort_keys=False), encoding="utf-8"
    )


def _approval_repository(tmp_path: Path) -> tuple[dict[str, object], str]:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "campaign@example.invalid")
    _git(tmp_path, "config", "user.name", "Campaign Test")
    shutil.copytree(model_layout.MODEL_ROOT, tmp_path / "model")
    schema_relative = model_layout.IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH.relative_to(
        model_layout.ROOT
    )
    schema_destination = tmp_path / schema_relative
    schema_destination.parent.mkdir(parents=True)
    shutil.copy2(model_layout.IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH, schema_destination)
    campaign = _pending_campaign()
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "candidate plan")
    plan_sha = _git(tmp_path, "rev-parse", "HEAD")

    checkpoint = f"approval:{plan_sha}"
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": checkpoint,
    }
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "approve campaign")
    return campaign, plan_sha


def _renewed_approval_repository(tmp_path: Path) -> tuple[dict[str, object], str]:
    """A corrected plan approved again while three slices are already complete."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "campaign@example.invalid")
    _git(tmp_path, "config", "user.name", "Campaign Test")
    shutil.copytree(model_layout.MODEL_ROOT, tmp_path / "model")
    schema_relative = model_layout.IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH.relative_to(
        model_layout.ROOT
    )
    schema_destination = tmp_path / schema_relative
    schema_destination.parent.mkdir(parents=True)
    shutil.copy2(model_layout.IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH, schema_destination)
    campaign = _replanned_campaign()
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "corrected candidate plan")
    plan_sha = _git(tmp_path, "rev-parse", "HEAD")

    _renew(campaign, checkpoint=f"approval:{plan_sha}")
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "renew campaign approval")
    return campaign, plan_sha


def test_renewed_approval_commit_binds_the_current_head_to_its_plan(tmp_path: Path) -> None:
    campaign, _ = _renewed_approval_repository(tmp_path)

    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []


def test_renewed_approval_commit_may_change_only_approval_state(tmp_path: Path) -> None:
    campaign, _ = _renewed_approval_repository(tmp_path)
    campaign["slices"][4]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "--amend", "-m", "renew campaign approval")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("beyond approval state" in finding for finding in findings)


def _complete_fourth_slice(campaign: dict[str, object], *, checkpoint: str) -> None:
    fourth = campaign["slices"][3]  # type: ignore[index]
    fourth["lifecycle"] = "complete"
    fourth["implementation_status"] = "conforming"
    fourth["evidence_refs"] = ["command:just check"]
    fourth["checkpoint"] = checkpoint
    campaign["slices"][4]["lifecycle"] = "ready"  # type: ignore[index]


def test_a_slice_finished_since_the_renewal_must_checkpoint_against_the_renewed_plan(
    tmp_path: Path,
) -> None:
    """The state a compliant agent would produce if the frontier alone were trusted.

    Nothing yet bears the renewed plan, so an in-record frontier has no anchor and the
    campaign checkpoint can stay on the approval. Only the approved plan's own record
    knows S004 was pending when the plan was reviewed.
    """
    campaign, _ = _renewed_approval_repository(tmp_path)
    _complete_fourth_slice(campaign, checkpoint=f"slice:S004:{SUPERSEDED_PLAN_SHORT_SHA}:1")
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "complete S004")

    assert implementation_campaign.validate_campaign(campaign, root=tmp_path) == []
    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("checkpoints against a superseded plan" in finding for finding in findings)


def test_a_slice_finished_since_the_renewal_binds_cleanly_under_the_renewed_plan(
    tmp_path: Path,
) -> None:
    campaign, plan_sha = _renewed_approval_repository(tmp_path)
    checkpoint = f"slice:S004:{plan_sha[:12]}:1"
    _complete_fourth_slice(campaign, checkpoint=checkpoint)
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "complete S004")

    assert implementation_campaign.validate_campaign(campaign, root=tmp_path) == []
    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []


def test_a_slice_completed_before_the_renewal_may_not_be_re_minted(tmp_path: Path) -> None:
    campaign, plan_sha = _renewed_approval_repository(tmp_path)
    campaign["slices"][2]["checkpoint"] = f"slice:S003:{plan_sha[:12]}:1"  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = campaign["slices"][2]["checkpoint"]  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "re-mint a completed slice")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("may not be re-minted" in finding for finding in findings)


def test_renewed_approval_commit_must_directly_follow_its_reviewed_plan(tmp_path: Path) -> None:
    campaign, _ = _renewed_approval_repository(tmp_path)
    (tmp_path / "NOTES.md").write_text("# Notes\n", encoding="utf-8")
    _git(tmp_path, "add", "NOTES.md")
    _git(tmp_path, "commit", "-m", "interpose an unrelated commit")
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "--allow-empty", "-m", "re-record the approval")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("must directly follow its approved plan" in finding for finding in findings)


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
    campaign = _pending_campaign()
    campaign["shadow_specification"] = {}  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("Additional properties are not allowed" in finding for finding in findings)


def test_schema_rejects_malformed_lifecycle_status() -> None:
    campaign = _pending_campaign()
    campaign["campaign"]["lifecycle"] = "running"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("campaign.lifecycle" in finding and "running" in finding for finding in findings)


def test_unapproved_campaign_cannot_enter_execution() -> None:
    campaign = _pending_campaign()
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "ready"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("unapproved plans" in finding for finding in findings)
    assert any("unapproved campaign" in finding for finding in findings)


def test_dependencies_must_exist_precede_and_remain_acyclic() -> None:
    campaign = _pending_campaign()
    first = campaign["slices"][0]  # type: ignore[index]
    second = campaign["slices"][1]  # type: ignore[index]
    first["dependencies"] = [second["id"]]
    second["dependencies"] = [first["id"], "S999"]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("unknown dependency S999" in finding for finding in findings)
    assert any("must have a lower order" in finding for finding in findings)
    assert any("dependency cycle" in finding for finding in findings)


def test_authority_and_slice_links_must_be_bidirectional() -> None:
    campaign = _pending_campaign()
    campaign["authority"][0]["slice_ids"].pop()  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("slice links are not bidirectional" in finding for finding in findings)


def test_qualified_authority_reference_is_bound_to_its_source_file() -> None:
    campaign = _pending_campaign()
    campaign["authority"][0]["refs"][0]["source"] = "model/50-verification.sysml"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("is owned by model/10-rtg-domain.sysml" in finding for finding in findings)


def test_realization_decision_ids_are_campaign_unique() -> None:
    campaign = _pending_campaign()
    decisions = [
        decision
        for entry in campaign["slices"]  # type: ignore[index]
        for decision in entry["realization_decisions"]
    ]
    decisions[1]["id"] = decisions[0]["id"]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("duplicate realization decision id" in finding for finding in findings)


def test_qualified_model_references_are_resolved_by_the_official_validator() -> None:
    campaign = _pending_campaign()
    campaign["authority"][0]["refs"][0]["model_ref"] = "RTG::'Definitely Missing'"  # type: ignore[index]

    findings = implementation_campaign.qualified_model_reference_findings(campaign)

    assert findings == ["qualified model reference does not resolve: RTG::'Definitely Missing'"]


def test_campaign_reference_check_uses_one_validator_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def resolve_once(references: list[str]) -> list[str]:
        calls.append(references)
        return []

    monkeypatch.setattr(sysml_validator, "unresolved_model_references", resolve_once)

    assert implementation_campaign.qualified_model_reference_findings(_campaign()) == []
    assert len(calls) == 1


def test_evidence_references_are_reproducible_project_references() -> None:
    campaign = _pending_campaign()
    campaign["authority"][0]["evidence_refs"] = [  # type: ignore[index]
        "a prose assertion",
        "path:/tmp/result.txt#case",
        "path:missing.txt#case",
        "path:docs#case",
        "path:README.md#definitely-not-a-real-section",
        "path:evidence\nspoof.md#case",
        "command: ",
        "command:just check\rmalicious second display line",
    ]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must use path: or command:" in finding for finding in findings)
    assert any("path:<repo-relative-path>" in finding for finding in findings)
    assert any("does not exist: missing.txt" in finding for finding in findings)
    assert any("does not exist: docs" in finding for finding in findings)
    assert any("evidence fragment does not resolve" in finding for finding in findings)
    assert any("one exact nonempty command" in finding for finding in findings)


def test_evidence_path_cannot_escape_through_an_ancestor_symlink(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    external = tmp_path / "external"
    repository.mkdir()
    external.mkdir()
    (external / "case.md").write_text("# Case\n", encoding="utf-8")
    (repository / "linked").symlink_to(external, target_is_directory=True)

    findings = implementation_campaign._evidence_reference_findings(
        "path:linked/case.md#case",
        label="slice.S001.evidence_refs[0]",
        root=repository,
    )

    assert any("escapes the repository through a symlink" in finding for finding in findings)


def test_checkpoint_formats_reject_active_markers_and_wrong_slice_ids() -> None:
    campaign = _pending_campaign()
    _approve(campaign)
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = "slice:S001:active"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][0]["checkpoint"] = f"slice:S002:{PLAN_SHA[:12]}:1"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("campaign checkpoint has an unsupported" in finding for finding in findings)
    assert any("slice S001 checkpoint names S002" in finding for finding in findings)
    assert any("active slice S001 must retain no checkpoint" in finding for finding in findings)


def test_awaiting_campaign_cannot_claim_a_recovery_checkpoint() -> None:
    campaign = _pending_campaign()
    campaign["campaign"]["checkpoint"] = f"slice:S017:{PLAN_SHA[:12]}:1"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "awaiting-approval campaign may not have a checkpoint" in finding for finding in findings
    )
    assert any("must match that completed slice's checkpoint" in finding for finding in findings)


def test_blocked_campaign_retains_its_latest_completed_slice_checkpoint() -> None:
    campaign = _pending_campaign()
    first = campaign["slices"][0]  # type: ignore[index]
    first_checkpoint = f"slice:S001:{PLAN_SHA[:12]}:1"
    first["lifecycle"] = "complete"
    first["implementation_status"] = "conforming"
    first["evidence_refs"] = ["path:README.md#development-setup"]
    first["checkpoint"] = first_checkpoint
    campaign["campaign"]["lifecycle"] = "blocked"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "changes-required",
        "checkpoint": None,
    }
    campaign["campaign"]["checkpoint"] = first_checkpoint  # type: ignore[index]
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "model gap",
        "summary": "A stakeholder-visible distinction is unresolved.",
        "authority_ids": ["A001"],
        "evidence_refs": [],
    }

    assert implementation_campaign.validate_campaign(campaign) == []

    campaign["campaign"]["checkpoint"] = f"slice:S017:{PLAN_SHA[:12]}:1"  # type: ignore[index]
    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must retain the latest completed slice" in finding for finding in findings)
    assert any("must match that completed slice's checkpoint" in finding for finding in findings)


def test_only_one_slice_may_be_active() -> None:
    campaign = _pending_campaign()
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    _approve(campaign)
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "active"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("at most one slice may be active" in finding for finding in findings)


def test_accepted_approval_must_enter_an_executable_lifecycle() -> None:
    campaign = _pending_campaign()
    _approve(campaign)

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "accepted approval requires a ready, active, or complete" in finding for finding in findings
    )


def test_human_authority_blocker_stops_execution_and_invalidates_approval() -> None:
    campaign = _pending_campaign()
    _approve(campaign)
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "model gap",
        "summary": "Stakeholder-visible meaning is unresolved.",
        "authority_ids": ["A001"],
        "evidence_refs": [],
    }

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must stop campaign execution" in finding for finding in findings)
    assert any("blocker invalidates approval" in finding for finding in findings)
    assert any("may not retain a blocker" in finding for finding in findings)


def test_ready_campaign_selects_only_the_lowest_dependency_ready_slice() -> None:
    campaign = _pending_campaign()
    _approve(campaign)
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "ready"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "not the lowest-ordered dependency-ready slice S001" in finding for finding in findings
    )


def test_interrupted_active_slice_retains_the_last_recoverable_checkpoint() -> None:
    campaign = _pending_campaign()
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    _approve(campaign)
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]

    assert implementation_campaign.validate_campaign(campaign) == []
    assert "Active: S001 " in implementation_campaign._status(campaign)


def test_active_campaign_uses_latest_completed_slice_checkpoint() -> None:
    campaign = _pending_campaign()
    _approve(campaign)
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    first = campaign["slices"][0]  # type: ignore[index]
    first["lifecycle"] = "complete"
    first["implementation_status"] = "conforming"
    first["evidence_refs"] = ["path:README.md#development-setup"]
    first["checkpoint"] = f"slice:S001:{PLAN_SHA[:12]}:1"
    campaign["slices"][1]["lifecycle"] = "active"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must be the latest recoverable checkpoint" in finding for finding in findings)


def test_renewed_approval_keeps_the_checkpoints_completed_slices_earned() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)

    assert implementation_campaign.validate_campaign(campaign) == []
    assert [entry["checkpoint"] for entry in campaign["slices"][:3]] == [  # type: ignore[index]
        f"slice:S00{index + 1}:{SUPERSEDED_PLAN_SHORT_SHA}:1" for index in range(3)
    ]


def test_renewed_approval_is_the_latest_recoverable_checkpoint_until_a_slice_completes() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    campaign["campaign"]["checkpoint"] = campaign["slices"][2]["checkpoint"]  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must be the latest recoverable checkpoint" in finding for finding in findings)


def test_a_slice_completed_under_a_renewed_plan_may_not_use_the_superseded_one() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    fourth = campaign["slices"][3]  # type: ignore[index]
    fourth["lifecycle"] = "complete"
    fourth["implementation_status"] = "conforming"
    fourth["evidence_refs"] = ["command:just check"]
    fourth["checkpoint"] = f"slice:S004:{SUPERSEDED_PLAN_SHORT_SHA}:1"
    campaign["campaign"]["checkpoint"] = fourth["checkpoint"]  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("campaign checkpoint must use the approved plan" in f for f in findings)


def test_a_slice_completed_under_the_renewed_plan_becomes_the_campaign_checkpoint() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    fourth = campaign["slices"][3]  # type: ignore[index]
    fourth["lifecycle"] = "complete"
    fourth["implementation_status"] = "conforming"
    fourth["evidence_refs"] = ["command:just check"]
    fourth["checkpoint"] = f"slice:S004:{PLAN_SHA[:12]}:1"
    campaign["campaign"]["checkpoint"] = fourth["checkpoint"]  # type: ignore[index]
    campaign["slices"][4]["lifecycle"] = "ready"  # type: ignore[index]

    assert implementation_campaign.validate_campaign(campaign) == []


def test_a_superseded_checkpoint_may_not_follow_one_earned_under_the_renewed_plan() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    for index, plan in ((3, PLAN_SHA[:12]), (4, SUPERSEDED_PLAN_SHORT_SHA)):
        entry = campaign["slices"][index]  # type: ignore[index]
        entry["lifecycle"] = "complete"
        entry["implementation_status"] = "conforming"
        entry["evidence_refs"] = ["command:just check"]
        entry["checkpoint"] = f"slice:S00{index + 1}:{plan}:1"
    campaign["campaign"]["checkpoint"] = campaign["slices"][4]["checkpoint"]  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("slice S005 checkpoint does not use the approved plan commit" in f for f in findings)


def test_a_superseded_checkpoint_is_rejected_between_two_earned_under_the_renewed_plan() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    for index, plan in ((3, PLAN_SHA[:12]), (4, SUPERSEDED_PLAN_SHORT_SHA), (5, PLAN_SHA[:12])):
        entry = campaign["slices"][index]  # type: ignore[index]
        entry["lifecycle"] = "complete"
        entry["implementation_status"] = "conforming"
        entry["evidence_refs"] = ["command:just check"]
        entry["checkpoint"] = f"slice:S00{index + 1}:{plan}:1"
    campaign["campaign"]["checkpoint"] = campaign["slices"][5]["checkpoint"]  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("slice S005 checkpoint does not use the approved plan commit" in f for f in findings)


def test_the_superseded_region_is_bounded_by_slice_order_not_record_order() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    for index, plan in ((3, PLAN_SHA[:12]), (4, SUPERSEDED_PLAN_SHORT_SHA)):
        entry = campaign["slices"][index]  # type: ignore[index]
        entry["lifecycle"] = "complete"
        entry["implementation_status"] = "conforming"
        entry["evidence_refs"] = ["command:just check"]
        entry["checkpoint"] = f"slice:S00{index + 1}:{plan}:1"
    campaign["campaign"]["checkpoint"] = campaign["slices"][3]["checkpoint"]  # type: ignore[index]
    entries: list[dict[str, object]] = campaign["slices"]  # type: ignore[assignment]
    entries[3], entries[4] = entries[4], entries[3]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("slice S005 checkpoint does not use the approved plan commit" in f for f in findings)


def test_only_a_complete_slice_may_carry_a_checkpoint() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    campaign["slices"][4]["checkpoint"] = f"slice:S005:{PLAN_SHA[:12]}:1"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("only a complete slice may carry a checkpoint: S005" in f for f in findings)


def test_renewed_approval_readies_only_the_next_dependency_ready_slice() -> None:
    expected = implementation_campaign._expected_approval_campaign(
        _replanned_campaign(), checkpoint=APPROVAL_CHECKPOINT
    )

    assert expected["campaign"]["checkpoint"] == APPROVAL_CHECKPOINT  # type: ignore[index]
    assert [
        entry["id"]
        for entry in expected["slices"]  # type: ignore[union-attr]
        if entry["lifecycle"] == "ready"
    ] == ["S004"]


def test_active_campaign_cannot_skip_a_lower_dependency_ready_slice() -> None:
    campaign = _pending_campaign()
    _approve(campaign)
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    first = campaign["slices"][0]  # type: ignore[index]
    first["lifecycle"] = "complete"
    first["implementation_status"] = "conforming"
    first["evidence_refs"] = ["path:README.md#development-setup"]
    first["checkpoint"] = f"slice:S001:{PLAN_SHA[:12]}:1"
    campaign["campaign"]["checkpoint"] = first["checkpoint"]  # type: ignore[index]
    campaign["slices"][2]["lifecycle"] = "active"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("active slice S003 is not the lowest-ordered" in finding for finding in findings)


def test_completed_slice_cannot_skip_lower_ordered_work() -> None:
    campaign = _pending_campaign()
    second = campaign["slices"][1]  # type: ignore[index]
    second["lifecycle"] = "complete"
    second["implementation_status"] = "conforming"
    second["evidence_refs"] = ["path:README.md#development-setup"]
    second["checkpoint"] = f"slice:S002:{PLAN_SHA[:12]}:1"

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "complete slice S002 skipped lower-ordered slices: S001" in finding for finding in findings
    )


def test_code_defect_cannot_masquerade_as_a_human_blocker() -> None:
    campaign = _pending_campaign()
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
    campaign = _pending_campaign()
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
    campaign = _pending_campaign()
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    _approve(campaign)
    first = campaign["slices"][0]  # type: ignore[index]
    first["lifecycle"] = "complete"
    first["implementation_status"] = "partial"

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must be conforming" in finding for finding in findings)
    assert any("requires evidence" in finding for finding in findings)
    assert any("requires a checkpoint" in finding for finding in findings)


def test_campaign_completion_requires_full_system_closure() -> None:
    campaign = _pending_campaign()
    campaign["campaign"]["lifecycle"] = "complete"  # type: ignore[index]
    _approve(campaign)
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

    campaign = _pending_campaign()
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
    status = implementation_campaign._status(_pending_campaign())

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


def test_status_reports_the_lowest_ordered_slice_blocker() -> None:
    campaign = _pending_campaign()
    campaign["slices"][0]["blocker"] = {  # type: ignore[index]
        "classification": "model gap",
        "summary": "A named distinction is unresolved.",
        "authority_ids": ["A001"],
        "evidence_refs": [],
    }

    status = implementation_campaign._status(campaign)

    assert "Blocker: S001 model gap: A named distinction is unresolved." in status


def test_approval_checkpoint_binds_the_current_head_to_its_plan(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)

    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []


def test_approval_checkpoint_cannot_change_the_reviewed_plan(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)
    campaign["slices"][0]["label"] = "A materially different first slice"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "drift the approved plan")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("changed plan-bearing content" in finding for finding in findings)


def test_checkpoint_check_rejects_dirty_tracked_state(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)
    path = tmp_path / "implementation-campaign.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("clean tracked working tree" in finding for finding in findings)


def test_checkpoint_check_rejects_a_working_record_that_differs_from_head(
    tmp_path: Path,
) -> None:
    campaign, _ = _approval_repository(tmp_path)
    campaign["campaign"]["objective"] = "A different objective"  # type: ignore[index]

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("does not match the campaign committed at HEAD" in finding for finding in findings)


def test_slice_checkpoint_uses_ordinary_commit_without_special_trailers(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    evidence = tmp_path / "evidence.md"
    evidence.write_text("# Case\n\nDiscriminating evidence.\n", encoding="utf-8")
    checkpoint = f"slice:S001:{plan_sha[:12]}:1"
    first = campaign["slices"][0]  # type: ignore[index]
    first["lifecycle"] = "complete"
    first["implementation_status"] = "conforming"
    first["evidence_refs"] = ["path:evidence.md#case"]
    first["checkpoint"] = checkpoint
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml", "evidence.md")
    _git(tmp_path, "commit", "-m", "complete S001")

    assert implementation_campaign.validate_campaign(campaign, root=tmp_path) == []
    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []


def test_current_checkpoint_requires_committed_evidence(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    evidence = tmp_path / "evidence.md"
    evidence.write_text("# Case\n\nDiscriminating evidence.\n", encoding="utf-8")
    checkpoint = f"slice:S001:{plan_sha[:12]}:1"
    first = campaign["slices"][0]  # type: ignore[index]
    first["lifecycle"] = "complete"
    first["implementation_status"] = "conforming"
    first["evidence_refs"] = ["path:evidence.md#case"]
    first["checkpoint"] = checkpoint
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "record S001 without its evidence")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("is not committed at HEAD" in finding for finding in findings)


def test_closure_checkpoint_binds_complete_current_state(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    evidence = tmp_path / "evidence.md"
    evidence.write_text("# Case\n\nDiscriminating evidence.\n", encoding="utf-8")
    for entry in campaign["slices"]:  # type: ignore[index]
        entry["lifecycle"] = "complete"
        entry["implementation_status"] = "conforming"
        entry["evidence_refs"] = ["path:evidence.md#case"]
        entry["checkpoint"] = f"slice:{entry['id']}:{plan_sha[:12]}:1"
    for authority in campaign["authority"]:  # type: ignore[index]
        authority["implementation_status"] = "conforming"
        authority["evidence_refs"] = ["path:evidence.md#case"]
    checkpoint = f"closure:{plan_sha[:12]}:1"
    campaign["campaign"]["lifecycle"] = "complete"  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    campaign["closure"]["integration_status"] = "conforming"  # type: ignore[index]
    campaign["closure"]["runnable_status"] = "conforming"  # type: ignore[index]
    campaign["closure"]["evidence_refs"] = ["path:evidence.md#case"]  # type: ignore[index]
    campaign["closure"]["checkpoint"] = checkpoint  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml", "evidence.md")
    _git(tmp_path, "commit", "-m", "close campaign")

    assert implementation_campaign.validate_campaign(campaign, root=tmp_path) == []
    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []
