from __future__ import annotations

import copy
from typing import Any, cast

import pytest
import yaml

from tools import system_evolution


def _record() -> dict[str, object]:
    return system_evolution.load_record()


# The live record is an execution index, not a fixture. Selecting by position in the
# dependency graph keeps these cases about the rule being validated, so naming the next
# evolution's work differently cannot fail a test that says nothing about names.
def _root_work(record: dict[str, object]) -> dict[str, Any]:
    """Return the earliest work item nothing else has to precede."""
    items = cast(list[dict[str, Any]], record["work_items"])
    return min(
        (item for item in items if not item["dependencies"]),
        key=lambda item: item["order"],
    )


def _dependent_work(record: dict[str, object]) -> dict[str, Any]:
    """Return the work item that depends on the root."""
    items = cast(list[dict[str, Any]], record["work_items"])
    root = _root_work(record)
    return next(item for item in items if root["id"] in item["dependencies"])


def _owned_finding(record: dict[str, object], work_id: str) -> dict[str, Any]:
    """Return one finding the named work item owns."""
    findings = cast(list[dict[str, Any]], record["findings"])
    return next(each for each in findings if each["owner_work_item_id"] == work_id)


def _active_work(record: dict[str, object]) -> dict[str, object]:
    items = cast(list[dict[str, Any]], record["work_items"])
    return next(item for item in items if item["lifecycle"] == "active")


def _active_record() -> dict[str, Any]:
    record = copy.deepcopy(system_evolution.load_record())
    implementation = f"git:{system_evolution._git_text(system_evolution.ROOT, 'rev-parse', 'HEAD')}"  # noqa: SLF001
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["observed"])
    for baseline in ("target", "observed"):
        record["baselines"][baseline]["implementation"] = implementation
        record["baselines"][baseline]["checkpoint"] = implementation
    for review in record["closure"]["reviews"]:
        review["checkpoint"] = implementation
    record["closure"]["checkpoint"] = implementation
    record["evolution"]["lifecycle"] = "active"
    record["evolution"]["checkpoint"] = None
    # Select the implementation item explicitly instead of depending on live ledger state.
    active = _root_work(record)
    active["planned_baseline"] = {
        "dimension": "implementation",
        "identity": implementation,
    }
    active["lifecycle"] = "active"
    active["implementation_status"] = "partial"
    active["evidence_refs"] = []
    active["checkpoint"] = None
    return record


def _complete_record() -> dict[str, Any]:
    record = copy.deepcopy(system_evolution.load_record())
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["observed"])
    checkpoint = record["baselines"]["target"]["implementation"]
    for finding in record["findings"]:
        finding["disposition"] = "resolved"
        finding["implementation_status"] = "conforming"
    for decision in record["decisions"]:
        decision["implementation_status"] = "conforming"
    for item in record["work_items"]:
        item["lifecycle"] = "complete"
        item["implementation_status"] = "conforming"
        item["checkpoint"] = checkpoint
        item["evidence_refs"] = item["evidence_refs"] or ["command:just check"]
    record["evolution"]["lifecycle"] = "complete"
    record["evolution"]["checkpoint"] = checkpoint
    record["closure"].update(
        finding_disposition="complete",
        model_status="accepted",
        implementation_status="conforming",
        integration_status="conforming",
        external_status="not applicable",
        checkpoint=checkpoint,
        evidence_refs=["command:just check"],
        reviews=[
            {
                "lens": lens,
                "status": "clean",
                "reviewer": f"agent:{index}",
                "checkpoint": checkpoint,
                "evidence_refs": ["command:just check"],
            }
            for index, lens in enumerate(record["scope"]["review_lenses"])
        ],
    )
    return record


def test_committed_evolution_record_is_valid() -> None:
    assert system_evolution.validate_record(_record()) == []


def test_qualified_authority_references_must_resolve_in_the_current_model() -> None:
    record = copy.deepcopy(_record())
    record["findings"][0]["authority_refs"] = [  # type: ignore[index]
        "VellisRequirements::doesNotExist"
    ]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any(
        "finding F001 authority reference does not resolve: "
        "VellisRequirements::doesNotExist" in finding
        for finding in findings
    )


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
    item = _root_work(record)
    item["lifecycle"] = "complete"
    item["implementation_status"] = "conforming"
    item["checkpoint"] = "git:checkpoint"
    finding = _owned_finding(record, item["id"])
    finding["disposition"] = "implementation-work"
    finding["implementation_status"] = "partial"

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any(f"complete work item {item['id']} has open findings" in each for each in findings)


def test_status_reports_the_active_item_before_another_ready_item() -> None:
    record = _active_record()
    report = system_evolution.status(record)  # type: ignore[arg-type]

    assert f"next_work: {_active_work(record)['id']}" in report


@pytest.mark.parametrize("lifecycle", ("ready", "complete"))
def test_executable_work_requires_complete_dependencies(lifecycle: str) -> None:
    record = copy.deepcopy(_record())
    _root_work(record)["lifecycle"] = "pending"
    dependent = _dependent_work(record)
    dependent["lifecycle"] = lifecycle

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any(
        f"{lifecycle} work item {dependent['id']} has incomplete dependencies" in each
        for each in findings
    )


def test_accepted_approval_requires_an_attributable_checkpoint() -> None:
    record = copy.deepcopy(_record())
    root = _root_work(record)
    root["approval"]["status"] = "accepted"
    root["approval"]["checkpoint"] = None

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert f"accepted approval for {root['id']} has no attributable checkpoint" in findings


def test_active_work_cannot_remain_bound_only_to_a_source_baseline() -> None:
    record = _active_record()
    active = _active_work(record)
    active["planned_baseline"] = {
        "dimension": "implementation",
        "identity": "git:ee86d59",
    }

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any(
        f"active work item {active['id']} has stale planned baseline" in each for each in findings
    )


def test_complete_closure_requires_named_evidenced_review_lenses() -> None:
    record = cast(dict[str, Any], copy.deepcopy(_record()))
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["observed"])
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
        checkpoint="git:da790ff",
        evidence_refs=["command:just check"],
        reviews=[
            {
                "lens": "foo",
                "status": "clean",
                "reviewer": "agent:foo",
                "checkpoint": "git:da790ff",
                "evidence_refs": ["command:just check"],
            },
            {
                "lens": "bar",
                "status": "clean",
                "reviewer": "agent:bar",
                "checkpoint": "git:da790ff",
                "evidence_refs": ["command:just check"],
            },
        ],
    )

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("lacks clean required review lenses" in each for each in findings)


def test_git_checkpoints_must_resolve_to_commits() -> None:
    record = cast(dict[str, Any], copy.deepcopy(_record()))
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["observed"])
    record["baselines"]["source"]["checkpoint"] = "git:does-not-exist"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "Git checkpoint does not resolve to a commit: git:does-not-exist" in findings


def test_complete_closure_rejects_duplicate_or_unresolved_reviews() -> None:
    record = cast(dict[str, Any], copy.deepcopy(_record()))
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["observed"])
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
                "reviewer": "agent:authority",
                "checkpoint": "git:da790ff",
                "evidence_refs": ["command:just model-check"],
            },
            {
                "lens": "engineering and evidence",
                "status": "findings",
                "reviewer": "agent:engineering-old",
                "checkpoint": "git:da790ff",
                "evidence_refs": ["command:just check"],
            },
            {
                "lens": "engineering and evidence",
                "status": "clean",
                "reviewer": "agent:engineering",
                "checkpoint": "git:da790ff",
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
    dependent = _dependent_work(record)
    shared = _owned_finding(record, _root_work(record)["id"])["id"]
    dependent["lifecycle"] = "blocked"
    dependent["blocker"] = {
        "classification": "external dependency",
        "summary": "The same bounded dependency blocks this work item.",
        "finding_ids": [shared],
        "evidence_refs": [],
    }
    dependent["finding_ids"].append(shared)

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "evolution blocker names unknown finding F999" in findings
    assert any(f"finding {shared} is listed by" in finding for finding in findings)


def test_duplicate_ids_are_rejected_before_indexing() -> None:
    record = copy.deepcopy(_record())
    duplicate = copy.deepcopy(record["findings"][0])  # type: ignore[index]
    duplicate["summary"] = "A shadow row must not replace the first finding."
    record["findings"].append(duplicate)  # type: ignore[union-attr]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "duplicate finding ID: F001" in findings


def test_observed_baseline_is_derived_from_the_repository() -> None:
    record = _active_record()
    initial_findings = system_evolution.validate_record(record)  # type: ignore[arg-type]
    assert (
        "observed implementation baseline does not match the current repository"
        not in initial_findings
    )
    assert (
        "observed checkpoint baseline does not match the current repository" not in initial_findings
    )
    record["baselines"]["target"]["implementation"] = "git:ee86d59"  # type: ignore[index]
    record["baselines"]["target"]["checkpoint"] = "git:ee86d59"  # type: ignore[index]
    record["baselines"]["observed"]["implementation"] = "git:ee86d59"  # type: ignore[index]
    record["baselines"]["observed"]["checkpoint"] = "git:ee86d59"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "observed implementation baseline does not match the current repository" in findings
    assert "observed checkpoint baseline does not match the current repository" in findings


def test_planned_baseline_names_one_dimension_not_any_matching_token() -> None:
    record = _active_record()
    active = _active_work(record)
    active["planned_baseline"] = {
        "dimension": "implementation",
        "identity": record["baselines"]["observed"]["execution_environment"],  # type: ignore[index]
    }

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any(
        f"active work item {active['id']} has stale planned baseline" in each for each in findings
    )


@pytest.mark.parametrize("identity_source", ("unknown", "implementation-token"))
def test_completed_work_rejects_unrecognized_or_cross_dimension_historical_baselines(
    identity_source: str,
) -> None:
    record = copy.deepcopy(_record())
    record["work_items"][0]["lifecycle"] = "complete"  # type: ignore[index]
    identity = (
        "superseded-model-baseline"
        if identity_source == "unknown"
        else record["baselines"]["observed"]["implementation"]  # type: ignore[index]
    )
    record["work_items"][0]["planned_baseline"] = {  # type: ignore[index]
        "dimension": "model",
        "identity": identity,
    }

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    first = cast(list[dict[str, Any]], record["work_items"])[0]["id"]
    assert f"complete work item {first} has an unrecognized historical planned baseline" in findings


def test_vellis_evidence_rejects_false_commands_and_unresolved_fragments() -> None:
    record = copy.deepcopy(_record())
    record["findings"][0]["evidence_refs"] = [  # type: ignore[index]
        "command:false",
        "path:tests/test_system_evolution.py#not_a_test",
    ]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("not a Vellis check" in each for each in findings)
    assert any("evidence fragment does not resolve" in each for each in findings)


def test_package_check_is_recognized_as_durable_vellis_evidence() -> None:
    assert system_evolution._is_vellis_check_command(  # noqa: SLF001
        "just package-check", root=system_evolution.ROOT
    )


def test_accepted_approval_checkpoint_must_exist_and_contain_the_gate() -> None:
    record = copy.deepcopy(_record())
    root = _root_work(record)
    root["approval"]["status"] = "accepted"
    root["approval"]["checkpoint"] = "git:does-not-exist"

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "Git checkpoint does not resolve to a commit: git:does-not-exist" in findings
    assert any("approval checkpoint is not reconstructible" in each for each in findings)


def test_every_finding_requires_one_completion_owner() -> None:
    record = copy.deepcopy(_record())
    record["findings"][0]["owner_work_item_id"] = None  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("owner_work_item_id" in each and "not of type 'string'" in each for each in findings)


def test_dependency_order_must_precede_the_dependent() -> None:
    record = copy.deepcopy(_record())
    dependent = _dependent_work(record)
    dependent["order"] = 1

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert (
        f"{dependent['id']} dependency {_root_work(record)['id']} must have a lower order"
        in findings
    )


def test_lifecycle_rollup_requires_matching_executable_or_approval_frontier() -> None:
    ready = copy.deepcopy(_record())
    ready["evolution"]["lifecycle"] = "ready"  # type: ignore[index]
    for item in cast(list[dict[str, Any]], ready["work_items"]):
        item["lifecycle"] = "pending"
        # The frontier these rules are about is what the record declares, not what the
        # live one happens to hold. Stating both preconditions here keeps the case about
        # the rollup rule, so an evolution that legitimately carries a pending approval
        # cannot satisfy the very rule this asserts fires.
        item["approval"] = {
            "status": "not-required",
            "reason": "Test frontier.",
            "checkpoint": None,
        }
    awaiting = copy.deepcopy(ready)
    awaiting["evolution"]["lifecycle"] = "awaiting-approval"  # type: ignore[index]

    ready_findings = system_evolution.validate_record(ready)  # type: ignore[arg-type]
    awaiting_findings = system_evolution.validate_record(awaiting)  # type: ignore[arg-type]

    assert "a ready evolution requires at least one ready work item" in ready_findings
    assert (
        "an awaiting-approval evolution requires a pending work-item approval" in awaiting_findings
    )


def test_completed_reviews_require_attribution_and_every_declared_lens() -> None:
    record = _complete_record()
    record["closure"]["reviews"][0]["reviewer"] = None  # type: ignore[index]
    record["closure"]["reviews"].pop()  # type: ignore[union-attr]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "review 'authority and conformance' lacks reviewer attribution" in findings


def test_clean_final_reviews_must_bind_the_exact_target_implementation() -> None:
    record = _complete_record()
    for review in record["closure"]["reviews"]:
        review["checkpoint"] = "git:da790ff"

    findings = system_evolution.validate_record(record)

    assert any("is not bound to the target implementation" in each for each in findings)


def test_accepted_approval_seals_its_owner_facing_consequence() -> None:
    record = copy.deepcopy(system_evolution.load_record())
    item = _root_work(record)
    item["approval"]["status"] = "accepted"
    item["approval"]["checkpoint"] = "git:does-not-exist"
    item["nearest_wrong_system"] = "A changed gated consequence."

    findings = system_evolution.validate_record(record)

    assert any("approval checkpoint is not reconstructible" in each for each in findings)


def test_complete_record_must_be_committed(monkeypatch: Any) -> None:
    record = _complete_record()
    original = system_evolution._git_text  # noqa: SLF001

    def dirty_record(root, *arguments):
        if arguments == ("status", "--porcelain", "--untracked-files=no"):
            return " M system-evolution.yaml"
        return original(root, *arguments)

    monkeypatch.setattr(system_evolution, "_git_text", dirty_record)

    findings = system_evolution.validate_record(record)

    assert "complete evolution has dirty tracked state outside its record" in findings


def test_pytest_evidence_targets_must_exist() -> None:
    record = copy.deepcopy(system_evolution.load_record())
    record["findings"][0]["evidence_refs"] = ["command:uv run pytest tests/does_not_exist.py"]

    findings = system_evolution.validate_record(record)

    assert any("not a Vellis check" in each for each in findings)


def test_out_of_scope_disposition_requires_evidence() -> None:
    record = copy.deepcopy(system_evolution.load_record())
    record["findings"][0]["disposition"] = "out-of-scope"
    record["findings"][0]["implementation_status"] = "conflicting"
    record["findings"][0]["evidence_refs"] = []

    findings = system_evolution.validate_record(record)

    assert "out-of-scope finding F001 has no disposition evidence" in findings


def test_an_accepted_approval_binds_to_a_checkpoint_that_had_the_decision_open() -> None:
    """Acceptance has to be recordable at all, and still has to mean something.

    Requiring the checkpoint to already show the approval accepted has no base case: the
    first such record could only point at a commit that already contained it. The state
    was unreachable, and no evolution in this repository ever recorded one. What the
    checkpoint can honestly carry is that the question was put, and that what was put has
    not changed since — git cannot witness a person saying yes, and a prior 'accepted' was
    only ever an earlier claim that they had.
    """
    record = copy.deepcopy(_record())
    item = _root_work(record)
    revision = system_evolution._git_text(system_evolution.ROOT, "rev-parse", "HEAD")  # noqa: SLF001
    committed = yaml.safe_load(
        system_evolution._git_text(  # noqa: SLF001
            system_evolution.ROOT, "show", f"{revision}:system-evolution.yaml"
        )
    )
    at_head = next(each for each in committed["work_items"] if each["id"] == item["id"])
    # Mirror the committed consequence, so only the approval state is under test.
    for field in ("label", "kind", "nearest_wrong_system", "compatibility_effect", "non_effects"):
        item[field] = at_head[field]
    item["approval"] = {
        "status": "accepted",
        "reason": at_head["approval"]["reason"],
        "checkpoint": f"git:{revision}",
    }

    open_at_checkpoint = at_head["approval"]["status"] in {"pending", "accepted"}
    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]
    unreachable = [each for each in findings if "absent from its checkpoint" in each]
    if open_at_checkpoint:
        assert not unreachable, findings
    else:
        # The committed item needed no decision, so claiming one against it is refused.
        assert any("not awaiting a decision" in each for each in findings), findings

    # Whatever the committed state, a changed consequence is still refused.
    item["approval"]["status"] = "accepted"
    item["nearest_wrong_system"] = "Something else entirely."
    changed = system_evolution.validate_record(record)  # type: ignore[arg-type]
    assert any(
        "differs from its approval checkpoint" in each or "not awaiting a decision" in each
        for each in changed
    ), changed
