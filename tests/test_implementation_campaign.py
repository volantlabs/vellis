from __future__ import annotations

import copy
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tools import implementation_campaign, model_layout

PLAN_SHA = "1" * 40
APPROVAL_CHECKPOINT = f"approval:{PLAN_SHA}"


def _campaign() -> dict[str, object]:
    return implementation_campaign.load_campaign(model_layout.IMPLEMENTATION_CAMPAIGN_PATH)


def _approve(campaign: dict[str, object]) -> None:
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": APPROVAL_CHECKPOINT,
    }
    campaign["campaign"]["checkpoint"] = APPROVAL_CHECKPOINT  # type: ignore[index]


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
    campaign = copy.deepcopy(_campaign())
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
    _git(
        tmp_path,
        "commit",
        "-m",
        "approve campaign",
        "-m",
        f"Campaign-Checkpoint: {checkpoint}\nCampaign-Approval: accepted",
    )
    return campaign, plan_sha


def _completed_repository(tmp_path: Path) -> tuple[dict[str, object], str]:
    campaign, plan_sha = _approval_repository(tmp_path)
    evidence = tmp_path / "evidence.md"
    evidence.write_text("# Case\n\nDiscriminating evidence.\n", encoding="utf-8")
    for index, entry in enumerate(campaign["slices"]):  # type: ignore[index]
        checkpoint = f"slice:{entry['id']}:{plan_sha[:12]}:1"
        entry["lifecycle"] = "complete"
        entry["implementation_status"] = "conforming"
        entry["evidence_refs"] = ["path:evidence.md#case"]
        entry["checkpoint"] = checkpoint
        if index + 1 < len(campaign["slices"]):  # type: ignore[arg-type,index]
            campaign["slices"][index + 1]["lifecycle"] = "ready"  # type: ignore[index]
        campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
        _write_campaign(tmp_path, campaign)
        _git(tmp_path, "add", "implementation-campaign.yaml", "evidence.md")
        _git(
            tmp_path,
            "commit",
            "-m",
            f"complete {entry['id']}",
            "-m",
            (
                f"Campaign-Checkpoint: {checkpoint}\n"
                "Campaign-Authority-Review: clean\n"
                "Campaign-Engineering-Review: clean"
            ),
        )
    return campaign, plan_sha


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


def test_qualified_authority_reference_is_bound_to_its_source_file() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["authority"][0]["refs"][0]["source"] = "model/50-verification.sysml"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("is owned by model/10-rtg-domain.sysml" in finding for finding in findings)


def test_authored_model_package_provenance_comes_from_file_content(tmp_path: Path) -> None:
    shutil.copytree(model_layout.MODEL_ROOT, tmp_path / "model")
    schema_relative = model_layout.IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH.relative_to(
        model_layout.ROOT
    )
    schema_destination = tmp_path / schema_relative
    schema_destination.parent.mkdir(parents=True)
    shutil.copy2(model_layout.IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH, schema_destination)
    first = tmp_path / "model/10-rtg-domain.sysml"
    second = tmp_path / "model/15-everyday-life-starter.sysml"
    first_source = first.read_text(encoding="utf-8")
    second_source = second.read_text(encoding="utf-8")
    first.write_text(second_source, encoding="utf-8")
    second.write_text(first_source, encoding="utf-8")
    campaign = copy.deepcopy(_campaign())
    observed = implementation_campaign.observed_baseline(tmp_path)
    campaign["model_baseline"]["planned"].update(observed)  # type: ignore[index]
    campaign["model_baseline"]["observed"].update(observed)  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(
        campaign,
        root=tmp_path,
        schema_path=schema_destination,
    )

    assert any("package provenance mismatch" in finding for finding in findings)


def test_realization_decision_ids_are_campaign_unique() -> None:
    campaign = copy.deepcopy(_campaign())
    decisions = [
        decision
        for entry in campaign["slices"]  # type: ignore[index]
        for decision in entry["realization_decisions"]
    ]
    decisions[1]["id"] = decisions[0]["id"]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("duplicate realization decision id" in finding for finding in findings)


def test_qualified_model_references_are_resolved_by_the_official_validator() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["authority"][0]["refs"][0]["model_ref"] = "RTG::'Definitely Missing'"  # type: ignore[index]

    findings = implementation_campaign.qualified_model_reference_findings(campaign)

    assert findings == ["qualified model reference does not resolve: RTG::'Definitely Missing'"]


def test_evidence_references_are_reproducible_project_references() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["authority"][0]["evidence_refs"] = [  # type: ignore[index]
        "a prose assertion",
        "path:/tmp/result.txt#case",
        "path:missing.txt#case",
        "path:docs#case",
        "path:README.md#definitely-not-a-real-section",
        "command: ",
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
    campaign = copy.deepcopy(_campaign())
    _approve(campaign)
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = "slice:S001:active"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][0]["checkpoint"] = f"slice:S002:{PLAN_SHA[:12]}:1"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("campaign checkpoint has an unsupported" in finding for finding in findings)
    assert any("slice S001 checkpoint names S002" in finding for finding in findings)
    assert any("active slice S001 must retain no checkpoint" in finding for finding in findings)


def test_only_one_slice_may_be_active() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    _approve(campaign)
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "active"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("at most one slice may be active" in finding for finding in findings)


def test_accepted_approval_must_enter_an_executable_lifecycle() -> None:
    campaign = copy.deepcopy(_campaign())
    _approve(campaign)

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "accepted approval requires a ready, active, or complete" in finding for finding in findings
    )


def test_human_authority_blocker_stops_execution_and_invalidates_approval() -> None:
    campaign = copy.deepcopy(_campaign())
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
    campaign = copy.deepcopy(_campaign())
    _approve(campaign)
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "ready"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "not the lowest-ordered dependency-ready slice S001" in finding for finding in findings
    )


def test_interrupted_active_slice_retains_the_last_recoverable_checkpoint() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    _approve(campaign)
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]

    assert implementation_campaign.validate_campaign(campaign) == []
    assert "Active: S001 " in implementation_campaign._status(campaign)


def test_active_campaign_uses_latest_completed_slice_checkpoint() -> None:
    campaign = copy.deepcopy(_campaign())
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


def test_active_campaign_cannot_skip_a_lower_dependency_ready_slice() -> None:
    campaign = copy.deepcopy(_campaign())
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
    campaign = copy.deepcopy(_campaign())
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
    campaign = copy.deepcopy(_campaign())
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


def test_status_reports_the_lowest_ordered_slice_blocker() -> None:
    campaign = copy.deepcopy(_campaign())
    campaign["slices"][0]["blocker"] = {  # type: ignore[index]
        "classification": "model gap",
        "summary": "A named distinction is unresolved.",
        "authority_ids": ["A001"],
        "evidence_refs": [],
    }

    status = implementation_campaign._status(campaign)

    assert "Blocker: S001 model gap: A named distinction is unresolved." in status


def test_approval_checkpoint_resolves_to_its_direct_plan_commit(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)

    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []


def test_approval_checkpoint_cannot_change_the_reviewed_plan(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    campaign["slices"][0]["label"] = "A materially different first slice"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    checkpoint = f"approval:{plan_sha}"
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(
        tmp_path,
        "commit",
        "--amend",
        "-m",
        "approve changed campaign",
        "-m",
        f"Campaign-Checkpoint: {checkpoint}\nCampaign-Approval: accepted",
    )

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("changed plan-bearing campaign content" in finding for finding in findings)


def test_slice_checkpoint_cannot_drift_from_the_approved_plan(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    evidence = tmp_path / "evidence.md"
    evidence.write_text("# Case\n\nDiscriminating evidence.\n", encoding="utf-8")
    checkpoint = f"slice:S001:{plan_sha[:12]}:1"
    first = campaign["slices"][0]  # type: ignore[index]
    first["verification_refs"].pop()
    first["lifecycle"] = "complete"
    first["implementation_status"] = "conforming"
    first["evidence_refs"] = ["path:evidence.md#case"]
    first["checkpoint"] = checkpoint
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml", "evidence.md")
    _git(
        tmp_path,
        "commit",
        "-m",
        "complete drifted S001",
        "-m",
        (
            f"Campaign-Checkpoint: {checkpoint}\n"
            "Campaign-Authority-Review: clean\n"
            "Campaign-Engineering-Review: clean"
        ),
    )

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("changed plan-bearing content after approval" in finding for finding in findings)


def test_historical_checkpoint_resolves_its_qualified_references(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    evidence = tmp_path / "evidence.md"
    evidence.write_text("# Case\n\nDiscriminating evidence.\n", encoding="utf-8")
    checkpoint = f"slice:S001:{plan_sha[:12]}:1"
    first = campaign["slices"][0]  # type: ignore[index]
    first["verification_refs"][0] = "VellisVerification::'Definitely Missing'"
    first["lifecycle"] = "complete"
    first["implementation_status"] = "conforming"
    first["evidence_refs"] = ["path:evidence.md#case"]
    first["checkpoint"] = checkpoint
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml", "evidence.md")
    _git(
        tmp_path,
        "commit",
        "-m",
        "complete S001 with a missing historical reference",
        "-m",
        (
            f"Campaign-Checkpoint: {checkpoint}\n"
            "Campaign-Authority-Review: clean\n"
            "Campaign-Engineering-Review: clean"
        ),
    )

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("Definitely Missing" in finding for finding in findings)


def test_current_checkpoint_must_be_the_exact_head_recovery_state(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)
    _git(tmp_path, "commit", "--allow-empty", "-m", "uncheckpointed work")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("not HEAD" in finding for finding in findings)


def test_slice_checkpoint_requires_both_clean_review_trailers(tmp_path: Path) -> None:
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
    _git(
        tmp_path,
        "commit",
        "-m",
        "complete S001",
        "-m",
        f"Campaign-Checkpoint: {checkpoint}",
    )

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("Campaign-Authority-Review: clean" in finding for finding in findings)
    assert any("Campaign-Engineering-Review: clean" in finding for finding in findings)


def test_checkpoint_rejects_contradictory_campaign_trailers(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    checkpoint = f"approval:{plan_sha}"
    _git(
        tmp_path,
        "commit",
        "--amend",
        "-m",
        "approve campaign with contradictory attestation",
        "-m",
        (
            f"Campaign-Checkpoint: {checkpoint}\n"
            "Campaign-Approval: rejected\n"
            "Campaign-Approval: accepted"
        ),
    )

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any(
        "requires exactly one canonical Campaign-Approval: accepted" in finding
        for finding in findings
    )


def test_checkpoint_rejects_case_variant_campaign_trailers(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    checkpoint = f"approval:{plan_sha}"
    _git(
        tmp_path,
        "commit",
        "--amend",
        "-m",
        "approve campaign with case-variant contradiction",
        "-m",
        (
            f"Campaign-Checkpoint: {checkpoint}\n"
            "Campaign-Approval: accepted\n"
            "campaign-approval: rejected"
        ),
    )

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any(
        "requires exactly one canonical Campaign-Approval: accepted" in finding
        for finding in findings
    )


def test_duplicate_checkpoint_trailers_are_not_resumable(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    checkpoint = f"approval:{plan_sha}"
    _git(
        tmp_path,
        "commit",
        "--allow-empty",
        "-m",
        "duplicate checkpoint",
        "-m",
        f"Campaign-Checkpoint: {checkpoint}",
    )

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("found 2" in finding for finding in findings)


def test_historical_symlink_blob_cannot_masquerade_as_evidence(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    evidence = tmp_path / "evidence.md"
    evidence.symlink_to("# Case")
    first_checkpoint = f"slice:S001:{plan_sha[:12]}:1"
    first = campaign["slices"][0]  # type: ignore[index]
    first["lifecycle"] = "complete"
    first["implementation_status"] = "conforming"
    first["evidence_refs"] = ["path:evidence.md#case"]
    first["checkpoint"] = first_checkpoint
    campaign["campaign"]["checkpoint"] = first_checkpoint  # type: ignore[index]
    campaign["slices"][1]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml", "evidence.md")
    _git(
        tmp_path,
        "commit",
        "-m",
        "complete S001 with symlink evidence",
        "-m",
        (
            f"Campaign-Checkpoint: {first_checkpoint}\n"
            "Campaign-Authority-Review: clean\n"
            "Campaign-Engineering-Review: clean"
        ),
    )

    evidence.unlink()
    evidence.write_text("# Case\n\nDiscriminating evidence.\n", encoding="utf-8")
    second_checkpoint = f"slice:S002:{plan_sha[:12]}:1"
    second = campaign["slices"][1]  # type: ignore[index]
    second["lifecycle"] = "complete"
    second["implementation_status"] = "conforming"
    second["evidence_refs"] = ["path:evidence.md#case"]
    second["checkpoint"] = second_checkpoint
    campaign["campaign"]["checkpoint"] = second_checkpoint  # type: ignore[index]
    campaign["slices"][2]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml", "evidence.md")
    _git(
        tmp_path,
        "commit",
        "-m",
        "complete S002 with regular evidence",
        "-m",
        (
            f"Campaign-Checkpoint: {second_checkpoint}\n"
            "Campaign-Authority-Review: clean\n"
            "Campaign-Engineering-Review: clean"
        ),
    )

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any(
        "must be a regular committed file; found mode 120000" in finding for finding in findings
    )


def test_missing_checkpoint_commit_is_not_resumable(tmp_path: Path) -> None:
    campaign, plan_sha = _approval_repository(tmp_path)
    checkpoint = f"slice:S001:{plan_sha[:12]}:1"
    campaign["slices"][0]["checkpoint"] = checkpoint  # type: ignore[index]

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any(checkpoint in finding and "found 0" in finding for finding in findings)


def test_closure_checkpoint_resolves_review_and_evidence(tmp_path: Path) -> None:
    campaign, plan_sha = _completed_repository(tmp_path)
    checkpoint = f"closure:{plan_sha[:12]}:1"
    campaign["campaign"]["lifecycle"] = "complete"  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]
    for authority in campaign["authority"]:  # type: ignore[index]
        authority["implementation_status"] = "conforming"
    campaign["closure"]["checkpoint"] = checkpoint  # type: ignore[index]
    campaign["closure"]["integration_status"] = "conforming"  # type: ignore[index]
    campaign["closure"]["runnable_status"] = "conforming"  # type: ignore[index]
    campaign["closure"]["evidence_refs"] = ["path:evidence.md#case"]  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(
        tmp_path,
        "commit",
        "-m",
        "close campaign",
        "-m",
        f"Campaign-Checkpoint: {checkpoint}\nCampaign-Closure-Review: clean",
    )

    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []
