from __future__ import annotations

import copy
from typing import Any, cast

import yaml

from tools import system_evolution


def _literal_baseline() -> dict[str, str]:
    return {
        "model": "sha256:synthetic-model",
        "implementation": "git:synthetic-implementation",
        "language": "sha256:synthetic-language",
        "execution_environment": "sha256:synthetic-environment",
        "checkpoint": "git:synthetic-implementation",
    }


def _record(baseline: dict[str, str] | None = None) -> dict[str, Any]:
    if baseline is None:
        baseline = system_evolution._repository_baseline(system_evolution.ROOT)  # noqa: SLF001
    return {
        "schema_version": "1.0",
        "evolution": {
            "id": "synthetic-evolution",
            "mode": "autonomous",
            "objective": "Exercise one synthetic evolution invariant.",
            "observable_distinction": "The validator accepts an independent minimal record.",
            "lifecycle": "planning",
            "approval": {
                "status": "not-required",
                "reason": "Synthetic validator evidence.",
                "checkpoint": None,
            },
            "blocker": None,
            "checkpoint": None,
        },
        "baselines": {
            "source": copy.deepcopy(baseline),
            "target": None,
        },
        "scope": {
            "authority_scope": ["AGENTS.md"],
            "implementation_scope": ["tools/system_evolution.py"],
            "review_lenses": ["authority and conformance", "engineering and evidence"],
            "non_goals": ["No product behavior."],
        },
        "findings": [
            {
                "id": "F001",
                "summary": "Synthetic open finding.",
                "classification": "implementation defect",
                "consequence": "A deliberately bounded validator consequence.",
                "authority_refs": ["AGENTS.md"],
                "evidence_refs": [],
                "disposition": "implementation-work",
                "owner_work_item_id": "W000",
            }
        ],
        "decisions": [
            {
                "id": "D001",
                "summary": "Use a synthetic record.",
                "authority_refs": ["AGENTS.md"],
                "alternatives": ["Use the live record."],
                "reversible": True,
                "owner_work_item_id": "W000",
                "implementation_status": "not evaluated",
                "evidence_refs": [],
            }
        ],
        "work_items": [
            {
                "id": "W000",
                "label": "Synthetic work",
                "kind": "implementation",
                "dependencies": [],
                "finding_ids": ["F001"],
                "decision_ids": ["D001"],
                "authority_refs": ["AGENTS.md"],
                "acceptance": [
                    {
                        "id": "A1",
                        "wrong_behavior": "The validator accepts an invalid record.",
                        "evidence_ref": "command:just check",
                    }
                ],
                "compatibility_effect": "No product compatibility effect.",
                "non_effects": ["No repository mutation."],
                "lifecycle": "pending",
                "implementation_status": "partial",
                "evidence_refs": ["command:just check"],
                "blocker": None,
                "checkpoint": None,
            }
        ],
        "reviews": [],
        "closure": {
            "model_status": "unchanged",
            "implementation_status": "partial",
            "compatibility": "No product compatibility effect.",
            "evidence_refs": [],
            "checkpoint": None,
        },
    }


def _root_work(record: dict[str, object]) -> dict[str, Any]:
    """Select the synthetic root by stable ID, never live position or topology."""
    return _work(record, "W000")


def _work(record: dict[str, object], work_id: str) -> dict[str, Any]:
    return next(
        item for item in cast(list[dict[str, Any]], record["work_items"]) if item["id"] == work_id
    )


def _finding(record: dict[str, object], finding_id: str) -> dict[str, Any]:
    return next(
        item for item in cast(list[dict[str, Any]], record["findings"]) if item["id"] == finding_id
    )


def _decision(record: dict[str, object], decision_id: str) -> dict[str, Any]:
    return next(
        item
        for item in cast(list[dict[str, Any]], record["decisions"])
        if item["id"] == decision_id
    )


def _dependent_work(record: dict[str, object]) -> dict[str, Any]:
    """Return or synthesize one work item that depends on the root."""
    items = cast(list[dict[str, Any]], record["work_items"])
    root = _root_work(record)
    existing = next(
        (item for item in items if root["id"] in item["dependencies"]),
        None,
    )
    if existing is not None:
        return existing
    dependent = copy.deepcopy(root)
    dependent.update(
        id="W_TEST_DEPENDENT",
        dependencies=[root["id"]],
        finding_ids=[],
        decision_ids=[],
        lifecycle="pending",
        implementation_status="not evaluated",
        evidence_refs=[],
        blocker=None,
        checkpoint=None,
    )
    items.append(dependent)
    return dependent


def _owned_finding(record: dict[str, object], work_id: str) -> dict[str, Any]:
    """Return one finding the named work item owns."""
    findings = cast(list[dict[str, Any]], record["findings"])
    return next(each for each in findings if each["owner_work_item_id"] == work_id)


def _active_work(record: dict[str, object]) -> dict[str, object]:
    items = cast(list[dict[str, Any]], record["work_items"])
    return next(item for item in items if item["lifecycle"] == "active")


def _active_record() -> dict[str, Any]:
    record = copy.deepcopy(_record())
    implementation = f"git:{system_evolution._git_text(system_evolution.ROOT, 'rev-parse', 'HEAD')}"  # noqa: SLF001
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["source"])
    record["baselines"]["target"]["implementation"] = implementation
    record["baselines"]["target"]["checkpoint"] = implementation
    for review in record["reviews"]:
        review["checkpoint"] = implementation
    record["closure"]["checkpoint"] = implementation
    record["evolution"]["lifecycle"] = "active"
    record["evolution"]["checkpoint"] = None
    # Select the implementation item explicitly instead of depending on live ledger state.
    active = _root_work(record)
    active["lifecycle"] = "active"
    active["implementation_status"] = "partial"
    active["evidence_refs"] = []
    active["checkpoint"] = None
    return record


def _complete_record() -> dict[str, Any]:
    record = copy.deepcopy(_record())
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["source"])
    checkpoint = record["baselines"]["target"]["implementation"]
    for finding in record["findings"]:
        finding["disposition"] = "resolved"
        finding["evidence_refs"] = ["command:just check"]
    for decision in record["decisions"]:
        decision["implementation_status"] = "conforming"
        decision["evidence_refs"] = ["command:just check"]
    for item in record["work_items"]:
        item["lifecycle"] = "complete"
        item["implementation_status"] = "conforming"
        item["checkpoint"] = checkpoint
        item["evidence_refs"] = item["evidence_refs"] or ["command:just check"]
    record["evolution"]["lifecycle"] = "complete"
    record["evolution"]["checkpoint"] = checkpoint
    record["closure"].update(
        model_status="accepted",
        implementation_status="conforming",
        checkpoint=checkpoint,
        evidence_refs=["command:just check"],
    )
    record["reviews"] = [
        {
            "lens": lens,
            "reviewer": f"agent:{index}",
            "checkpoint": checkpoint,
            "scope": "closure",
            "status": "clean",
            "evidence_refs": ["command:just check"],
        }
        for index, lens in enumerate(record["scope"]["review_lenses"])
    ]
    return record


def test_committed_evolution_record_is_valid() -> None:
    revision = system_evolution.repository.git_text(system_evolution.ROOT, "rev-parse", "HEAD")
    source = system_evolution.repository.git_text(
        system_evolution.ROOT, "show", f"{revision}:system-evolution.yaml"
    )

    assert system_evolution.validate_record(yaml.safe_load(source)) == []


def test_schema_requires_work_and_at_least_one_finding_or_decision() -> None:
    without_work = _record()
    without_work["work_items"] = []
    without_owned_concern = _record()
    without_owned_concern["findings"] = []
    without_owned_concern["decisions"] = []

    work_findings = system_evolution.validate_record(without_work)
    concern_findings = system_evolution.validate_record(without_owned_concern)

    assert any("work_items" in item and "non-empty" in item for item in work_findings)
    assert any("not valid under any" in item for item in concern_findings)


def test_pure_invariants_do_not_consult_git_or_repository_state(monkeypatch: Any) -> None:
    from tools.system_evolution_record import invariant_findings

    def fail_if_called(_root):
        raise AssertionError("pure invariant validation consulted repository state")

    monkeypatch.setattr(system_evolution.repository, "repository_baseline", fail_if_called)
    record = _record(_literal_baseline())
    _work(record, "W000")["finding_ids"].append("F999")

    assert "W000 owns unknown finding F999" in invariant_findings(record)


def test_qualified_authority_references_must_resolve_in_the_current_model() -> None:
    record = copy.deepcopy(_record())
    _finding(record, "F001")["authority_refs"] = ["VellisRequirements::doesNotExist"]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any(
        "finding F001 authority reference does not resolve: "
        "VellisRequirements::doesNotExist" in finding
        for finding in findings
    )


def test_unknown_owned_finding_is_rejected() -> None:
    record = copy.deepcopy(_record())
    _work(record, "W000")["finding_ids"].append("F999")
    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]
    assert any("owns unknown finding F999" in finding for finding in findings)


def test_only_one_work_item_may_be_active() -> None:
    record = copy.deepcopy(_record())
    _root_work(record)["lifecycle"] = "active"
    _dependent_work(record)["lifecycle"] = "active"
    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]
    assert "more than one work item is active" in findings


def test_resolved_findings_and_conforming_decisions_require_evidence() -> None:
    record = copy.deepcopy(_record())
    finding = _finding(record, "F001")
    finding["disposition"] = "resolved"
    finding["evidence_refs"] = []
    decision = _decision(record, "D001")
    decision["implementation_status"] = "conforming"
    decision["evidence_refs"] = []

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

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any(f"complete work item {item['id']} has open findings" in each for each in findings)


def test_status_reports_the_active_item_before_another_ready_item() -> None:
    record = _active_record()
    report = system_evolution.status(record)  # type: ignore[arg-type]

    assert f"next_work: {_active_work(record)['id']}" in report


def test_complete_closure_requires_named_evidenced_review_lenses() -> None:
    record = cast(dict[str, Any], copy.deepcopy(_record()))
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["source"])
    for item in record["work_items"]:  # type: ignore[union-attr]
        item["lifecycle"] = "complete"
        item["implementation_status"] = "conforming"
        item["checkpoint"] = "git:complete"
    record["evolution"]["lifecycle"] = "complete"  # type: ignore[index]
    record["evolution"]["checkpoint"] = "git:complete"  # type: ignore[index]
    record["baselines"]["target"]["checkpoint"] = "git:complete"  # type: ignore[index]
    record["baselines"]["target"]["checkpoint"] = "git:complete"  # type: ignore[index]
    closure = record["closure"]  # type: ignore[index]
    closure.update(  # type: ignore[union-attr]
        model_status="accepted",
        implementation_status="conforming",
        checkpoint="git:da790ff",
        evidence_refs=["command:just check"],
    )
    record["reviews"] = [
        {
            "scope": "closure",
            "lens": "foo",
            "status": "clean",
            "reviewer": "agent:foo",
            "checkpoint": "git:da790ff",
            "evidence_refs": ["command:just check"],
        },
        {
            "scope": "closure",
            "lens": "bar",
            "status": "clean",
            "reviewer": "agent:bar",
            "checkpoint": "git:da790ff",
            "evidence_refs": ["command:just check"],
        },
    ]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("lacks clean required review lenses" in each for each in findings)


def test_git_checkpoints_must_resolve_to_commits() -> None:
    record = cast(dict[str, Any], copy.deepcopy(_record()))
    if record["baselines"]["target"] is None:
        record["baselines"]["target"] = copy.deepcopy(record["baselines"]["source"])
    record["baselines"]["source"]["checkpoint"] = "git:does-not-exist"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "Git checkpoint does not resolve to a commit: git:does-not-exist" in findings


def test_closure_reads_the_latest_review_per_lens() -> None:
    """Repeated lenses are legal so the record can say what was already cleared.

    A lens that reported findings and later reported clean has been satisfied. Rejecting
    the repeat forced every pair to start from a record that could not express it.
    """
    record = _complete_record()
    checkpoint = record["baselines"]["target"]["implementation"]
    superseded = copy.deepcopy(record["reviews"][0])
    superseded["status"] = "findings"
    record["reviews"].insert(0, superseded)

    accepted = system_evolution.validate_record(record)

    assert not any("unresolved reviews" in each for each in accepted)

    trailing = copy.deepcopy(record["reviews"][-1])
    trailing["status"] = "findings"
    trailing["checkpoint"] = checkpoint
    record["reviews"].append(trailing)

    rejected = system_evolution.validate_record(record)

    assert any("unresolved reviews" in each for each in rejected)


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
    duplicate = copy.deepcopy(_finding(record, "F001"))
    duplicate["summary"] = "A shadow row must not replace the first finding."
    record["findings"].append(duplicate)  # type: ignore[union-attr]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "duplicate finding ID: F001" in findings


def test_model_baseline_is_derived_from_the_repository() -> None:
    """The repository is the observation; only the bound baseline is recorded."""
    record = _active_record()

    assert not any(
        "stale model baseline" in each
        for each in system_evolution.validate_record(record)  # type: ignore[arg-type]
    )

    record["baselines"]["target"]["model"] = "sha256:not-the-current-model"  # type: ignore[index]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "evolution is bound to a stale model baseline" in findings


def test_vellis_evidence_rejects_false_commands_and_unresolved_fragments() -> None:
    record = copy.deepcopy(_record())
    _finding(record, "F001")["evidence_refs"] = [
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


def test_every_finding_requires_one_completion_owner() -> None:
    record = copy.deepcopy(_record())
    _finding(record, "F001")["owner_work_item_id"] = None

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert any("owner_work_item_id" in each and "not of type 'string'" in each for each in findings)


def test_lifecycle_rollup_requires_matching_executable_or_approval_frontier() -> None:
    ready = copy.deepcopy(_record())
    ready["evolution"]["lifecycle"] = "ready"  # type: ignore[index]
    for item in cast(list[dict[str, Any]], ready["work_items"]):
        item["lifecycle"] = "pending"
    awaiting = copy.deepcopy(ready)
    awaiting["evolution"]["lifecycle"] = "awaiting-approval"  # type: ignore[index]
    # The frontier is what the record declares, not what the live one happens to hold.
    awaiting["evolution"]["approval"]["status"] = "pending"  # type: ignore[index]

    ready_findings = system_evolution.validate_record(ready)  # type: ignore[arg-type]
    awaiting_findings = system_evolution.validate_record(awaiting)  # type: ignore[arg-type]

    assert "a ready evolution requires at least one ready work item" in ready_findings
    assert "an awaiting-approval evolution requires a pending approval" not in awaiting_findings


def test_completed_reviews_require_attribution_and_every_declared_lens() -> None:
    record = _complete_record()
    record["reviews"][0]["reviewer"] = None  # type: ignore[index]
    record["reviews"].pop()  # type: ignore[union-attr]

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert "review 'authority and conformance' lacks reviewer attribution" in findings


def test_clean_final_reviews_must_bind_the_exact_target_implementation() -> None:
    record = _complete_record()
    for review in record["reviews"]:
        review["checkpoint"] = "git:da790ff"

    findings = system_evolution.validate_record(record)

    assert any("is not bound to the target implementation" in each for each in findings)


def test_complete_record_must_be_committed(monkeypatch: Any) -> None:
    record = _complete_record()
    original = system_evolution.repository.git_text
    dirty = False

    def dirty_record(root, *arguments):
        if arguments == ("status", "--porcelain", "--untracked-files=no"):
            return " M system-evolution.yaml" if dirty else ""
        return original(root, *arguments)

    monkeypatch.setattr(system_evolution.repository, "git_text", dirty_record)

    clean_findings = system_evolution.repository.repository_baseline_findings(
        record, root=system_evolution.ROOT
    )
    dirty = True
    dirty_findings = system_evolution.repository.repository_baseline_findings(
        record, root=system_evolution.ROOT
    )

    assert "complete evolution has dirty tracked state outside its record" not in clean_findings
    assert "complete evolution has dirty tracked state outside its record" in dirty_findings


def test_pytest_evidence_targets_must_exist() -> None:
    record = copy.deepcopy(_record())
    _finding(record, "F001")["evidence_refs"] = ["command:uv run pytest tests/does_not_exist.py"]

    findings = system_evolution.validate_record(record)

    assert any("not a Vellis check" in each for each in findings)


def test_out_of_scope_disposition_requires_evidence() -> None:
    record = copy.deepcopy(_record())
    finding = _finding(record, "F001")
    finding["disposition"] = "out-of-scope"
    finding["evidence_refs"] = []

    findings = system_evolution.validate_record(record)

    assert "out-of-scope finding F001 has no disposition evidence" in findings


def test_an_accepted_approval_binds_and_seals_owned_meaning(monkeypatch: Any) -> None:
    """Acceptance has to be recordable at all, and still has to mean something.

    Requiring the checkpoint to already show the approval accepted has no base case: the
    first such record could only point at a commit that already contained it. What the
    checkpoint can honestly carry is that the question was put, and that what was put has
    not changed since.

    Per-item approval is gone; one evolution approval seals the whole consequence, and the
    accepted model commit is the approval artifact for changed meaning.
    """
    historical = _record()
    historical["evolution"]["approval"] = {
        "status": "pending",
        "reason": "Approve the synthetic consequence.",
        "checkpoint": None,
    }
    record = copy.deepcopy(historical)
    revision = system_evolution.repository.git_text(system_evolution.ROOT, "rev-parse", "HEAD")
    record["evolution"]["approval"] = {
        "status": "accepted",
        "reason": "Approve the synthetic consequence.",
        "checkpoint": f"git:{revision}",
    }
    monkeypatch.setattr(
        system_evolution.repository,
        "_historical_record",
        lambda _revision, _root: copy.deepcopy(historical),
    )

    unchanged = system_evolution.validate_record(record)
    assert not any("approval" in each for each in unchanged), unchanged

    record["evolution"]["objective"] = "Pursue a materially different objective."
    changed = system_evolution.validate_record(record)

    assert any("differs from its approval checkpoint" in each for each in changed), changed


def test_evolution_approval_allows_later_not_required_internal_decision(monkeypatch: Any) -> None:
    historical = _record()
    historical["evolution"]["approval"] = {
        "status": "pending",
        "reason": "Approve the owner-facing evolution consequence.",
        "checkpoint": None,
    }
    record = copy.deepcopy(historical)
    revision = system_evolution.repository.git_text(system_evolution.ROOT, "rev-parse", "HEAD")
    record["evolution"]["approval"] = {
        "status": "accepted",
        "reason": "Approve the owner-facing evolution consequence.",
        "checkpoint": f"git:{revision}",
    }
    internal = _dependent_work(record)
    internal["decision_ids"] = ["D002"]
    record["decisions"].append(
        {
            "id": "D002",
            "summary": "Choose one reversible internal representation.",
            "authority_refs": ["AGENTS.md"],
            "alternatives": ["Choose another equivalent representation."],
            "reversible": True,
            "owner_work_item_id": internal["id"],
            "evidence_intent": ["The selected representation preserves current meaning."],
            "implementation_status": "not evaluated",
            "evidence_refs": [],
        }
    )
    monkeypatch.setattr(
        system_evolution.repository,
        "_historical_record",
        lambda _revision, _root: copy.deepcopy(historical),
    )

    findings = system_evolution.validate_record(record)

    assert not any("evolution consequence differs" in item for item in findings), findings


def test_every_acceptance_entry_binds_one_carried_evidence_reference() -> None:
    """Done is a property of the artifact: each acceptance entry names evidence it carries."""
    record = copy.deepcopy(_record())
    item = _root_work(record)
    item["acceptance"].append(
        {
            "id": "A2",
            "wrong_behavior": "The validator accepts an acceptance entry with no evidence.",
            "evidence_ref": "command:just lint",
        }
    )

    findings = system_evolution.validate_record(record)  # type: ignore[arg-type]

    assert (
        "acceptance W000.A2 names evidence the work item does not carry: command:just lint"
        in findings
    )


def test_complete_work_cannot_carry_evidence_no_acceptance_entry_claims() -> None:
    record = _complete_record()
    item = _root_work(record)
    item["evidence_refs"] = [*item["evidence_refs"], "command:just lint"]

    findings = system_evolution.validate_record(record)

    assert (
        "complete work item W000 carries evidence no acceptance entry claims: command:just lint"
        in findings
    )
