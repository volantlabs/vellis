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
    observed = implementation_campaign.observed_baseline()
    campaign["model_baseline"]["status"] = "current"  # type: ignore[index]
    campaign["model_baseline"]["planned"] = {  # type: ignore[index]
        **observed,
        "checkpoint": None,
    }
    campaign["model_baseline"]["observed"] = {  # type: ignore[index]
        **observed,
        "checkpoint": None,
    }
    for entry in campaign["authority"]:  # type: ignore[union-attr]
        entry["implementation_status"] = "absent"
        entry["evidence_refs"] = []
    for entry in campaign["slices"]:  # type: ignore[union-attr]
        entry["lifecycle"] = "pending"
        entry["implementation_status"] = "absent"
        entry["evidence_refs"] = []
        for decision in entry["realization_decisions"]:
            decision["implementation_status"] = "absent"
            decision["evidence_refs"] = []
        entry["blocker"] = None
        entry["checkpoint"] = None
    closure = campaign["closure"]
    closure["integration_status"] = "absent"  # type: ignore[index]
    closure["runnable_status"] = "absent"  # type: ignore[index]
    for decision in closure["realization_decisions"]:  # type: ignore[index]
        decision["implementation_status"] = "absent"
        decision["evidence_refs"] = []
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
        for decision in entry["realization_decisions"]:
            decision["implementation_status"] = "conforming"
            decision["evidence_refs"] = ["command:just check"]
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


def _conform_owned_decisions(entry: dict[str, object], evidence: str) -> None:
    """Close every decision owned by a test fixture work item with attributable evidence."""
    evidence_refs = entry["evidence_refs"]
    assert isinstance(evidence_refs, list)
    if evidence not in evidence_refs:
        evidence_refs.append(evidence)
    decisions = entry["realization_decisions"]
    assert isinstance(decisions, list)
    for decision in decisions:
        decision["implementation_status"] = "conforming"
        decision["evidence_refs"] = [evidence]


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
    for decision in fourth["realization_decisions"]:
        decision["implementation_status"] = "conforming"
        decision["evidence_refs"] = ["command:just check"]
    fourth["checkpoint"] = checkpoint
    campaign["slices"][4]["lifecycle"] = "ready"  # type: ignore[index]
    _reconcile_settled_authority(campaign)


def _finished_campaign() -> dict[str, object]:
    """An approved campaign whose every slice has completed and whose roll-ups agree.

    This is the state closure runs in, and the one the settled-roll-up rule speaks about.
    It validates cleanly, so a test can move exactly one value and see what the checker
    makes of it.
    """
    campaign = _pending_campaign()
    for entry in campaign["slices"]:  # type: ignore[union-attr]
        entry["lifecycle"] = "complete"
        entry["implementation_status"] = "conforming"
        entry["evidence_refs"] = ["command:just check"]
        for decision in entry["realization_decisions"]:
            decision["implementation_status"] = "conforming"
            decision["evidence_refs"] = ["command:just check"]
        entry["checkpoint"] = f"slice:{entry['id']}:{PLAN_SHA[:12]}:1"
    _reconcile_settled_authority(campaign)
    campaign["campaign"]["lifecycle"] = "ready"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "accepted",
        "checkpoint": APPROVAL_CHECKPOINT,
    }
    campaign["campaign"]["checkpoint"] = campaign["slices"][-1]["checkpoint"]  # type: ignore[index]
    return campaign


def _blocked_campaign() -> dict[str, object]:
    """A finished campaign that stopped, with its blocker naming A001."""
    campaign = _finished_campaign()
    campaign["campaign"]["lifecycle"] = "blocked"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {"status": "changes-required", "checkpoint": None}  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = campaign["slices"][-1]["checkpoint"]  # type: ignore[index]
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "plan gap",
        "summary": "the runnable boundary is unsettled",
        "authority_ids": ["A001"],
        "evidence_refs": ["command:just check"],
    }
    return campaign


def _reconcile_settled_authority(campaign: dict[str, object]) -> None:
    """Roll up any authority whose contributing slices have all completed.

    Completing a slice can settle an aggregate row, and a real campaign reconciles it in
    the same checkpoint. These fixtures are about checkpoint labelling, so they do it here
    rather than leaving a stale roll-up the checker would rightly report.
    """
    lifecycles = {
        entry["id"]: entry["lifecycle"]
        for entry in campaign["slices"]  # type: ignore[union-attr]
    }
    for entry in campaign["authority"]:  # type: ignore[union-attr]
        if all(lifecycles[slice_id] == "complete" for slice_id in entry["slice_ids"]):
            entry["implementation_status"] = "conforming"
            entry["evidence_refs"] = ["command:just check"]


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


def test_an_approval_commit_may_not_also_complete_a_slice(tmp_path: Path) -> None:
    campaign, plan_sha = _renewed_approval_repository(tmp_path)
    _complete_fourth_slice(campaign, checkpoint=f"slice:S004:{plan_sha[:12]}:1")
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "--amend", "-m", "renew approval and complete S004")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("beyond approval state" in finding for finding in findings)


def test_a_blocked_campaign_may_not_retain_an_unreachable_approval(tmp_path: Path) -> None:
    campaign, _ = _renewed_approval_repository(tmp_path)
    campaign["campaign"]["lifecycle"] = "blocked"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {"status": "changes-required", "checkpoint": None}  # type: ignore[index]
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "model gap",
        "summary": "A named distinction is unresolved.",
        "authority_ids": ["A001"],
        "evidence_refs": [],
    }
    campaign["slices"][3]["lifecycle"] = "pending"  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = f"approval:{'a' * 40}"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "block the campaign")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("retained approval commit does not exist" in finding for finding in findings)


def _block_at(campaign: dict[str, object], *, checkpoint: str) -> None:
    campaign["campaign"]["lifecycle"] = "blocked"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {"status": "changes-required", "checkpoint": None}  # type: ignore[index]
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "model gap",
        "summary": "A named distinction is unresolved.",
        "authority_ids": ["A001"],
        "evidence_refs": [],
    }
    campaign["slices"][3]["lifecycle"] = "pending"  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]


def test_a_blocked_campaign_may_retain_an_approval_granted_after_its_completed_slices(
    tmp_path: Path,
) -> None:
    campaign, plan_sha = _renewed_approval_repository(tmp_path)
    _block_at(campaign, checkpoint=f"approval:{plan_sha}")
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "block the campaign")

    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []


def test_a_blocked_campaign_may_not_retain_an_approval_its_slices_ran_past(
    tmp_path: Path,
) -> None:
    campaign, plan_sha = _renewed_approval_repository(tmp_path)
    completed = f"slice:S004:{plan_sha[:12]}:1"
    _complete_fourth_slice(campaign, checkpoint=completed)
    campaign["campaign"]["checkpoint"] = completed  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "complete S004")
    # Falling back to the approval now points recovery behind S004's own commit.
    _block_at(campaign, checkpoint=f"approval:{plan_sha}")
    campaign["slices"][3]["lifecycle"] = "complete"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "block the campaign")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("retained approval predates completed slices: S004" in f for f in findings)


def test_a_blocked_campaign_may_not_retain_an_approval_off_the_current_history(
    tmp_path: Path,
) -> None:
    campaign, plan_sha = _renewed_approval_repository(tmp_path)
    _git(tmp_path, "checkout", "-q", "-b", "aside", plan_sha)
    (tmp_path / "NOTES.md").write_text("# Notes\n", encoding="utf-8")
    _git(tmp_path, "add", "NOTES.md")
    _git(tmp_path, "commit", "-m", "an approval on another branch")
    aside = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", "-q", "-")
    _block_at(campaign, checkpoint=f"approval:{aside}")
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "block the campaign")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("retained approval commit is not an ancestor of HEAD" in f for f in findings)


def test_a_second_replan_distinguishes_each_generation_of_completed_slices(
    tmp_path: Path,
) -> None:
    """Three plan generations: the first two stay frozen, work since the third must be current."""
    campaign, first_plan = _renewed_approval_repository(tmp_path)
    second_checkpoint = f"slice:S004:{first_plan[:12]}:1"
    _complete_fourth_slice(campaign, checkpoint=second_checkpoint)
    campaign["campaign"]["checkpoint"] = second_checkpoint  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "complete S004 under the second plan")

    campaign["campaign"]["lifecycle"] = "awaiting-plan-approval"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {"status": "pending", "checkpoint": None}  # type: ignore[index]
    campaign["campaign"]["checkpoint"] = None  # type: ignore[index]
    campaign["slices"][4]["lifecycle"] = "pending"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "third candidate plan")
    third_plan = _git(tmp_path, "rev-parse", "HEAD")

    _renew(campaign, checkpoint=f"approval:{third_plan}")
    campaign["slices"][3]["lifecycle"] = "complete"  # type: ignore[index]
    campaign["slices"][4]["lifecycle"] = "ready"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "renew approval on the third plan")

    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []

    # A slice finished under generation three may not wear generation two's label.
    fifth = campaign["slices"][4]  # type: ignore[index]
    fifth["lifecycle"] = "complete"
    fifth["implementation_status"] = "conforming"
    fifth["evidence_refs"] = ["command:just check"]
    fifth["checkpoint"] = f"slice:S005:{first_plan[:12]}:1"
    campaign["campaign"]["checkpoint"] = fifth["checkpoint"]  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "complete S005 against a superseded plan")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("S005 completed under this approval but checkpoints" in f for f in findings)
    # Generation two's own label stays frozen rather than being read as a re-mint.
    assert not any("may not be re-minted" in finding for finding in findings)


def test_renewed_approval_commit_must_directly_follow_its_reviewed_plan(tmp_path: Path) -> None:
    campaign, plan_sha = _renewed_approval_repository(tmp_path)
    _git(tmp_path, "reset", "--hard", plan_sha)
    (tmp_path / "NOTES.md").write_text("# Notes\n", encoding="utf-8")
    _git(tmp_path, "add", "NOTES.md")
    _git(tmp_path, "commit", "-m", "interpose an unrelated commit")
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "grant approval one commit too late")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("must directly follow its approved plan" in finding for finding in findings)


def test_an_ordinary_commit_while_ready_is_not_judged_as_the_approval(tmp_path: Path) -> None:
    """The window between approval and the next slice is not commit-frozen.

    The record still rests on its approval checkpoint here, so a predicate reading only
    the record would judge every later commit as the approval it is not.
    """
    campaign, _ = _renewed_approval_repository(tmp_path)
    (tmp_path / "NOTES.md").write_text("# Notes\n", encoding="utf-8")
    _git(tmp_path, "add", "NOTES.md")
    _git(tmp_path, "commit", "-m", "fix documentation while the campaign waits")

    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []


def test_an_approval_commit_may_not_decline_the_rules_by_claiming_another_lifecycle(
    tmp_path: Path,
) -> None:
    campaign, plan_sha = _renewed_approval_repository(tmp_path)
    _git(tmp_path, "reset", "--hard", plan_sha)
    _renew(campaign, checkpoint=f"approval:{plan_sha}")
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][3]["lifecycle"] = "active"  # type: ignore[index]
    (tmp_path / "src.py").write_text("# unreviewed implementation\n", encoding="utf-8")
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "approve and start work in one commit")

    findings = implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path)

    assert any("must change only the campaign record" in finding for finding in findings)
    assert any("beyond approval state" in finding for finding in findings)


def test_committed_campaign_is_stale_and_valid() -> None:
    campaign = _campaign()

    assert implementation_campaign.validate_campaign(campaign) == []
    assert campaign["campaign"]["lifecycle"] == "stale"  # type: ignore[index]
    assert campaign["model_baseline"]["status"] == "stale"  # type: ignore[index]
    assert campaign["model_baseline"]["observed"] == {  # type: ignore[index]
        **implementation_campaign.observed_baseline(),
        "checkpoint": None,
    }
    assert (
        campaign["model_baseline"]["planned"]["authority_sha256"]  # type: ignore[index]
        != campaign["model_baseline"]["observed"]["authority_sha256"]  # type: ignore[index]
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


def test_a_settled_authority_may_not_stay_unevaluated_absent_or_partial() -> None:
    """Nothing but closure reconciles a roll-up, so the checker has to notice a stale one.

    Five aggregate rows sat at ``partial`` after every slice contributing to them had
    completed and been reviewed. Each slice was right about its own contribution and no
    rule compared them, so the record understated finished work until closure read it.
    """
    campaign = _finished_campaign()
    campaign["authority"][0]["implementation_status"] = "partial"  # type: ignore[index]
    campaign["authority"][1]["implementation_status"] = "conflicting"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "authority A001 is partial with every contributing slice complete" in finding
        for finding in findings
    )
    assert not any("authority A002" in finding for finding in findings)


def test_a_paused_campaign_may_say_an_authority_is_still_unfinished() -> None:
    """Stating the exact open disposition is the whole point of pausing.

    The settled-roll-up rule exists to stop an executing campaign from understating work it
    already finished. A campaign that has stopped is doing the opposite: naming what is not
    done. Closure's own guidance requires that a campaign with authority still absent,
    partial, or unevaluated stay open and say so.
    """
    campaign = _blocked_campaign()
    campaign["authority"][0]["implementation_status"] = "partial"  # type: ignore[index]

    assert implementation_campaign.validate_campaign(campaign) == []


def test_a_pause_excuses_only_the_authority_its_blocker_names() -> None:
    """Otherwise a blocked record becomes somewhere to park settled work unnoticed.

    Stating the exact disposition is what earns the latitude, so the latitude reaches
    exactly as far as the statement does. A second row quietly reverted to partial under
    the same blocker is the original defect wearing a pause.
    """
    campaign = _blocked_campaign()
    campaign["authority"][0]["implementation_status"] = "partial"  # type: ignore[index]
    campaign["authority"][1]["implementation_status"] = "partial"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert findings == [
        "authority A002 is partial with every contributing slice complete and no blocker naming it"
    ]


def test_an_authority_a_blocker_names_may_not_also_read_conforming() -> None:
    """The record cannot both stop on an authority and claim it conforms."""
    campaign = _blocked_campaign()
    campaign["authority"][0]["implementation_status"] = "conforming"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert findings == ["authority A001 is conforming and blocked at the same time"]


def test_partly_planned_authority_is_not_settled_by_finishing_its_slices() -> None:
    campaign = _finished_campaign()
    campaign["authority"][0]["planned_coverage"] = "partial"  # type: ignore[index]
    campaign["authority"][0]["implementation_status"] = "partial"  # type: ignore[index]
    campaign["closure"]["authority_coverage"] = "partial"  # type: ignore[index]

    assert implementation_campaign.validate_campaign(campaign) == []


def test_a_conforming_authority_needs_every_contributing_slice_complete() -> None:
    campaign = _pending_campaign()
    campaign["authority"][0]["implementation_status"] = "conforming"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "authority A001 is conforming with an incomplete contributing slice" in finding
        for finding in findings
    )


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


def test_completed_slice_cannot_hide_an_open_selected_decision() -> None:
    campaign = _finished_campaign()
    decision = campaign["slices"][0]["realization_decisions"][0]  # type: ignore[index]
    decision["implementation_status"] = "absent"
    decision["evidence_refs"] = []

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("complete slice S001 decision D002 must be conforming" in f for f in findings)
    assert any("complete slice S001 decision D002 requires evidence" in f for f in findings)


def test_decision_evidence_must_be_attributable_to_its_owner() -> None:
    campaign = _pending_campaign()
    decision = campaign["slices"][0]["realization_decisions"][0]  # type: ignore[index]
    decision["implementation_status"] = "conforming"
    decision["evidence_refs"] = ["command:just check"]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("decision D002 evidence must also be slice evidence" in f for f in findings)


def test_decision_authority_must_resolve_and_belong_to_the_owning_slice() -> None:
    campaign = _pending_campaign()
    decision = campaign["slices"][0]["realization_decisions"][0]  # type: ignore[index]
    decision["authority_ids"] = ["A999"]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("decision has unknown authority A999" in f for f in findings)

    decision["authority_ids"] = ["A013"]
    findings = implementation_campaign.validate_campaign(campaign)
    assert any("names authority A013 outside the slice contribution" in f for f in findings)


def test_closure_decision_evidence_must_be_closure_attributable() -> None:
    campaign = _pending_campaign()
    decision = campaign["closure"]["realization_decisions"][0]  # type: ignore[index]
    decision["implementation_status"] = "conforming"
    decision["evidence_refs"] = ["command:just check"]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any(
        "closure decision D003 evidence must also be closure evidence" in f for f in findings
    )


def test_closure_decision_ids_share_the_campaign_namespace() -> None:
    campaign = _pending_campaign()
    campaign["closure"]["realization_decisions"][0]["id"] = "D002"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("duplicate realization decision id: D002" in f for f in findings)


def test_plan_projection_freezes_decision_owner_but_not_execution_state() -> None:
    campaign = _pending_campaign()
    progressed = copy.deepcopy(campaign)
    decision = progressed["slices"][0]["realization_decisions"][0]  # type: ignore[index]
    decision["implementation_status"] = "conforming"
    decision["evidence_refs"] = ["command:just check"]

    assert implementation_campaign._plan_projection(progressed) == (
        implementation_campaign._plan_projection(campaign)
    )

    moved = copy.deepcopy(campaign)
    decision = moved["slices"][0]["realization_decisions"].pop()  # type: ignore[index]
    moved["closure"]["realization_decisions"].append(decision)  # type: ignore[index]
    assert implementation_campaign._plan_projection(moved) != (
        implementation_campaign._plan_projection(campaign)
    )

    changed_intent = copy.deepcopy(campaign)
    changed_intent["slices"][0]["realization_decisions"][0]["evidence_intent"] = [  # type: ignore[index]
        "Exclude a different wrong realization."
    ]
    assert implementation_campaign._plan_projection(changed_intent) != (
        implementation_campaign._plan_projection(campaign)
    )


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
    _conform_owned_decisions(first, "path:README.md#development-setup")
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
    _conform_owned_decisions(first, "path:README.md#development-setup")
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
    checkpoint = f"slice:S004:{PLAN_SHA[:12]}:1"
    _complete_fourth_slice(campaign, checkpoint=checkpoint)
    campaign["campaign"]["checkpoint"] = checkpoint  # type: ignore[index]

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


def _block(campaign: dict[str, object]) -> None:
    campaign["campaign"]["lifecycle"] = "blocked"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {"status": "changes-required", "checkpoint": None}  # type: ignore[index]
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "model gap",
        "summary": "A named distinction is unresolved.",
        "authority_ids": ["A001"],
        "evidence_refs": [],
    }
    campaign["slices"][3]["lifecycle"] = "pending"  # type: ignore[index]


def test_a_campaign_blocked_after_a_renewal_keeps_the_approval_it_reached() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    _block(campaign)

    assert implementation_campaign.validate_campaign(campaign) == []


def test_a_blocked_campaign_may_not_fall_back_behind_its_completed_slices() -> None:
    campaign = _replanned_campaign()
    _renew(campaign)
    _block(campaign)
    # The approval those three slices were completed under; resting here loses the replan.
    campaign["campaign"]["checkpoint"] = f"approval:{SUPERSEDED_PLAN_SHORT_SHA}{'0' * 28}"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("must retain the latest completed slice" in finding for finding in findings)


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
    _conform_owned_decisions(first, "path:README.md#development-setup")
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
        "Slices: pending=18",
        "Active: none",
        "Next: none",
        "Blocker: none",
        (
            "Open decisions: D002@S001, D001@S009, D007@S009, D004@S018, "
            "D005@S018, D003@closure, D006@closure"
        ),
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
    _conform_owned_decisions(first, "path:evidence.md#case")
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
    _conform_owned_decisions(first, "path:evidence.md#case")
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
        _conform_owned_decisions(entry, "path:evidence.md#case")
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
    _conform_owned_decisions(campaign["closure"], "path:evidence.md#case")  # type: ignore[arg-type]
    campaign["closure"]["checkpoint"] = checkpoint  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml", "evidence.md")
    _git(tmp_path, "commit", "-m", "close campaign")

    assert implementation_campaign.validate_campaign(campaign, root=tmp_path) == []
    assert implementation_campaign.checkpoint_binding_findings(campaign, root=tmp_path) == []


def test_dispatch_launches_only_the_ready_slice_and_binds_a_state_token(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)

    packet = implementation_campaign.dispatch_packet(campaign, root=tmp_path)

    assert packet["action"] == "launch-slice"
    assert packet["work_item"] == "S001"
    assert packet["worktree"]["status"] == "clean"
    assert len(packet["state_token"]) == 64


def test_dispatch_token_changes_when_the_ready_slice_becomes_active(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)
    first = implementation_campaign.dispatch_packet(campaign, root=tmp_path)
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "activate S001")

    second = implementation_campaign.dispatch_packet(campaign, root=tmp_path)

    assert second["action"] == "resume-slice"
    assert second["work_item"] == "S001"
    assert second["state_token"] != first["state_token"]


def test_dispatch_resumes_dirty_work_only_for_an_active_slice(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "activate S001")
    (tmp_path / "work.py").write_text("# active work\n", encoding="utf-8")

    packet = implementation_campaign.dispatch_packet(campaign, root=tmp_path)

    assert packet["action"] == "resume-slice"
    assert "active-slice-has-working-state" in packet["reason_codes"]


def test_dispatch_token_changes_when_dirty_work_changes(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]
    _write_campaign(tmp_path, campaign)
    _git(tmp_path, "add", "implementation-campaign.yaml")
    _git(tmp_path, "commit", "-m", "activate S001")
    work = tmp_path / "work.py"
    work.write_text("first\n", encoding="utf-8")
    first = implementation_campaign.dispatch_packet(campaign, root=tmp_path)

    work.write_text("second\n", encoding="utf-8")
    second = implementation_campaign.dispatch_packet(campaign, root=tmp_path)

    assert first["state_token"] != second["state_token"]


def test_dispatch_stops_on_dirty_state_without_an_active_slice(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)
    (tmp_path / "unexplained.py").write_text("# unexplained\n", encoding="utf-8")

    packet = implementation_campaign.dispatch_packet(campaign, root=tmp_path)

    assert packet["action"] == "stop-dirty"
    assert packet["work_item"] is None


def test_dispatch_stops_after_three_identical_launcher_failures(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)

    packet = implementation_campaign.dispatch_packet(campaign, root=tmp_path, identical_failures=3)

    assert packet["action"] == "await-human"
    assert "identical-failure-limit-reached" in packet["reason_codes"]


def test_dispatch_reports_invalid_campaign_state_without_selecting_work(tmp_path: Path) -> None:
    campaign, _ = _approval_repository(tmp_path)

    packet = implementation_campaign.dispatch_packet(
        campaign, root=tmp_path, validation_findings=["broken campaign"]
    )

    assert packet["action"] == "stop-invalid"
    assert packet["work_item"] is None
    assert packet["errors"] == ["broken campaign"]


def test_dispatch_awaits_human_when_approval_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign, _ = _approval_repository(tmp_path)
    campaign["campaign"]["plan_approval"] = {  # type: ignore[index]
        "status": "pending",
        "checkpoint": None,
    }
    monkeypatch.setattr(
        implementation_campaign, "checkpoint_binding_findings", lambda *_a, **_k: []
    )

    packet = implementation_campaign.dispatch_packet(campaign, root=tmp_path)

    assert packet["action"] == "await-human"
    assert "approval-required" in packet["reason_codes"]


@pytest.mark.parametrize(
    ("lifecycle", "expected_action"),
    (("ready", "launch-closure"), ("complete", "complete")),
)
def test_dispatch_distinguishes_closure_from_completed_campaign(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lifecycle: str,
    expected_action: str,
) -> None:
    campaign, _ = _approval_repository(tmp_path)
    campaign["campaign"]["lifecycle"] = lifecycle  # type: ignore[index]
    for entry in campaign["slices"]:  # type: ignore[index]
        entry["lifecycle"] = "complete"
    monkeypatch.setattr(
        implementation_campaign, "checkpoint_binding_findings", lambda *_a, **_k: []
    )

    packet = implementation_campaign.dispatch_packet(campaign, root=tmp_path)

    assert packet["action"] == expected_action
    assert packet["work_item"] == "closure"


def test_dispatch_cannot_launch_closure_past_an_open_slice_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign, _ = _approval_repository(tmp_path)
    for entry in campaign["slices"]:  # type: ignore[index]
        entry["lifecycle"] = "complete"
        entry["implementation_status"] = "conforming"
        entry["evidence_refs"] = ["command:just check"]
        _conform_owned_decisions(entry, "command:just check")
    decision = campaign["slices"][0]["realization_decisions"][0]  # type: ignore[index]
    decision["implementation_status"] = "partial"
    decision["evidence_refs"] = []
    findings = implementation_campaign.validate_campaign(campaign)
    monkeypatch.setattr(
        implementation_campaign, "checkpoint_binding_findings", lambda *_a, **_k: []
    )

    packet = implementation_campaign.dispatch_packet(
        campaign, root=tmp_path, validation_findings=findings
    )

    assert packet["action"] == "stop-invalid"
    assert "validation-failed" in packet["reason_codes"]


def test_complete_campaign_requires_closure_owned_decisions() -> None:
    campaign = _finished_campaign()
    campaign["campaign"]["lifecycle"] = "complete"  # type: ignore[index]

    findings = implementation_campaign.validate_campaign(campaign)

    assert any("requires closure decision D006 conforming" in f for f in findings)
    assert any("requires closure decision D006 evidence" in f for f in findings)


def test_review_frames_are_lens_specific_and_contain_no_review_history() -> None:
    campaign = _pending_campaign()
    _approve(campaign)
    campaign["campaign"]["lifecycle"] = "active"  # type: ignore[index]
    campaign["slices"][0]["lifecycle"] = "active"  # type: ignore[index]

    authority = implementation_campaign.review_frame(campaign, slice_id="S001", lens="authority")
    engineering = implementation_campaign.review_frame(
        campaign, slice_id="S001", lens="engineering"
    )

    assert "qualified model meaning" in authority
    assert "implementation correctness" in engineering
    assert "S001" in authority and "S001" in engineering
    assert "previous reviewer" not in authority.lower()
    assert "expected conclusion" not in engineering.lower()
    assert "invent novel mutants" in authority
    assert "Decisions this slice must close" in authority
    assert "D002 (absent)" in authority


def test_slice_review_frame_separates_owned_and_inherited_decisions() -> None:
    campaign = _pending_campaign()
    campaign["slices"][-1]["lifecycle"] = "active"  # type: ignore[index]

    frame = implementation_campaign.review_frame(campaign, slice_id="S018", lens="engineering")

    assert "Decisions this slice must close" in frame
    assert "D004 (absent)" in frame and "D005 (absent)" in frame
    assert "Inherited decisions this slice must preserve" in frame
    assert "D002 (absent from S001)" in frame
    assert "D001 (absent from S009)" in frame
    assert "Decision-attributable evidence" in frame
    assert "Planned decision evidence intent" in frame
    assert "Closure decisions still awaiting execution" in frame
    assert "D006 (absent)" in frame


def test_the_closure_work_item_gets_a_frame_of_its_own() -> None:
    """Dispatch names ``closure`` as a work item, so a frame has to exist for it.

    Closure is not a slice, and asking for one by that name used to fail as an unknown
    slice ID, leaving the item the campaign ends on with no way to generate its two fixed
    review prompts.
    """
    campaign = _finished_campaign()

    authority = implementation_campaign.review_frame(campaign, slice_id="closure", lens="authority")
    engineering = implementation_campaign.review_frame(
        campaign, slice_id="closure", lens="engineering"
    )

    assert "aggregate authority universe" in authority
    assert "integration across slices" in engineering
    assert "runnable status:" in authority and "runnable status:" in engineering
    assert "A018" in authority
    assert "D006" in engineering
    assert "invent novel mutants" in engineering
    assert "previous reviewer" not in authority.lower()
    assert "expected conclusion" not in engineering.lower()


def test_a_closure_frame_renders_a_blockers_shape_but_not_its_summary() -> None:
    """A blocker summary is the writer's own reading, and a fixed frame does not repeat it.

    Both lenses read the same frame, so quoting the diagnosis and its prescribed resolution
    into it is how one opinion becomes two agreeing ones. Classification and the authority
    named are state; the prose is a finding.

    This bounds what the frame itself writes, and nothing more. A reviewer following the
    frame's own evidence references and AGENTS.md will still read the campaign's recorded
    status in the repository's own words, which is what truthful documentation is for; the
    frame is not a way to keep a reviewer from finding out where the campaign stands.
    """
    campaign = _finished_campaign()
    campaign["campaign"]["lifecycle"] = "blocked"  # type: ignore[index]
    campaign["campaign"]["plan_approval"] = {"status": "changes-required", "checkpoint": None}  # type: ignore[index]
    campaign["campaign"]["blocker"] = {  # type: ignore[index]
        "classification": "plan gap",
        "summary": "the sky is falling and the only fix is to rewrite S009",
        "authority_ids": ["A017"],
        "evidence_refs": ["command:just check"],
    }

    for lens in ("authority", "engineering"):
        frame = implementation_campaign.review_frame(campaign, slice_id="closure", lens=lens)
        assert "classification: plan gap" in frame
        assert "A017" in frame
        assert "the sky is falling" not in frame


def test_a_closure_frame_needs_every_slice_finished_first() -> None:
    campaign = _pending_campaign()

    with pytest.raises(ValueError, match="requires every slice complete"):
        implementation_campaign.review_frame(campaign, slice_id="closure", lens="authority")


def test_worker_result_contract_is_compact_and_rejects_transcripts() -> None:
    result = {
        "schema_version": 1,
        "campaign_id": "example",
        "work_item": "S014",
        "outcome": "checkpointed",
        "checkpoint": "slice:S014:123456789abc:1",
        "checks": [{"name": "project gate", "outcome": "passed"}],
        "review_pairs": 2,
        "material_findings": [
            {"pair": 1, "authority": 1, "engineering": 0},
            {"pair": 2, "authority": 0, "engineering": 0},
        ],
        "elapsed_seconds": 42,
        "reason": None,
    }

    assert implementation_campaign.worker_result_findings(result) == []

    result["reviewer_transcript"] = "large hidden context"
    findings = implementation_campaign.worker_result_findings(result)
    assert any("Additional properties" in finding for finding in findings)


def test_checkpointed_worker_result_requires_both_review_pairs() -> None:
    result = {
        "schema_version": 1,
        "campaign_id": "example",
        "work_item": "S014",
        "outcome": "checkpointed",
        "checkpoint": "slice:S014:123456789abc:1",
        "checks": [{"name": "project gate", "outcome": "passed"}],
        "review_pairs": 1,
        "material_findings": [{"pair": 1, "authority": 0, "engineering": 0}],
        "elapsed_seconds": 42,
        "reason": None,
    }

    findings = implementation_campaign.worker_result_findings(result)

    assert any(
        "review_pairs" in finding and "less than the minimum of 2" in finding
        for finding in findings
    )
