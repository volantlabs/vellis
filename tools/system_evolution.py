from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator

try:
    from .implementation_campaign import (
        UniqueKeyLoader,
        _evidence_reference_findings,
        _sha256,
        authority_digest,
    )
    from .model_layout import ROOT, SYSTEM_EVOLUTION_PATH, SYSTEM_EVOLUTION_SCHEMA_PATH
except ImportError:  # pragma: no cover - direct script execution
    from implementation_campaign import (  # type: ignore[no-redef]
        UniqueKeyLoader,
        _evidence_reference_findings,
        _sha256,
        authority_digest,
    )
    from model_layout import (  # type: ignore[no-redef]
        ROOT,
        SYSTEM_EVOLUTION_PATH,
        SYSTEM_EVOLUTION_SCHEMA_PATH,
    )


def load_record(path: Path = SYSTEM_EVOLUTION_PATH) -> dict[str, Any]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)  # noqa: S506
    if not isinstance(value, dict):
        raise ValueError(f"{path}: evolution record must be a YAML mapping")
    return cast(dict[str, Any], value)


def _schema(path: Path = SYSTEM_EVOLUTION_SCHEMA_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: schema must be a JSON object")
    Draft202012Validator.check_schema(value)
    return cast(dict[str, Any], value)


def _json_path(parts: Any) -> str:
    return ".".join(str(part) for part in parts) or "record"


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _cycle_findings(work: dict[str, dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(work_id: str, trail: list[str]) -> None:
        if work_id in visited:
            return
        if work_id in visiting:
            start = trail.index(work_id)
            findings.append("work-item dependency cycle: " + " -> ".join([*trail[start:], work_id]))
            return
        visiting.add(work_id)
        trail.append(work_id)
        for dependency in work[work_id]["dependencies"]:
            if dependency in work:
                visit(dependency, trail)
        trail.pop()
        visiting.remove(work_id)
        visited.add(work_id)

    for work_id in work:
        visit(work_id, [])
    return findings


def _reference_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    findings: list[str] = []
    refs: list[tuple[str, str]] = []
    if record["evolution"]["blocker"] is not None:
        refs.extend(
            ("evolution blocker", reference)
            for reference in record["evolution"]["blocker"]["evidence_refs"]
        )
    for finding in record["findings"]:
        refs.extend(
            (f"finding {finding['id']}", reference) for reference in finding["evidence_refs"]
        )
    for decision in record["decisions"]:
        refs.extend(
            (f"decision {decision['id']}", reference) for reference in decision["evidence_refs"]
        )
    for item in record["work_items"]:
        refs.extend((f"work item {item['id']}", reference) for reference in item["evidence_refs"])
        if item["blocker"] is not None:
            refs.extend(
                (f"work item {item['id']} blocker", reference)
                for reference in item["blocker"]["evidence_refs"]
            )
    refs.extend(("closure", reference) for reference in record["closure"]["evidence_refs"])
    for review in record["closure"]["reviews"]:
        refs.extend(
            (f"review {review['lens']}", reference) for reference in review["evidence_refs"]
        )
    for label, reference in refs:
        findings.extend(_evidence_reference_findings(reference, label=label, root=root))
        if reference.startswith("command:") and not _is_vellis_check_command(
            reference.removeprefix("command:")
        ):
            findings.append(f"{label} command evidence is not a Vellis check: {reference}")
    return findings


def _is_vellis_check_command(command: str) -> bool:
    if command in {
        "just check",
        "just implementation-campaign-check",
        "just model-check",
        "just system-evolution-check",
        "just skills-check",
    }:
        return True
    return command.startswith("uv run pytest tests/") and not any(
        token in command for token in ("\n", "\r", ";", "&&", "||", "`", "$(")
    )


def _git_checkpoint_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    references: set[str] = set()
    for baseline_name in ("source", "target", "observed"):
        baseline = record["baselines"][baseline_name]
        if baseline is not None:
            references.update(
                value
                for value in baseline.values()
                if isinstance(value, str) and value.startswith("git:")
            )
    for item in record["work_items"]:
        for value in (
            item["planned_baseline"]["identity"],
            item["checkpoint"],
            item["approval"]["checkpoint"],
        ):
            if isinstance(value, str) and value.startswith("git:"):
                references.add(value)
    for review in record["closure"]["reviews"]:
        if isinstance(review["checkpoint"], str) and review["checkpoint"].startswith("git:"):
            references.add(review["checkpoint"])
    for value in (
        record["evolution"]["approval"]["checkpoint"],
        record["evolution"]["checkpoint"],
        record["closure"]["checkpoint"],
    ):
        if isinstance(value, str) and value.startswith("git:"):
            references.add(value)
    findings: list[str] = []
    for reference in sorted(references):
        revision = reference.removeprefix("git:")
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            findings.append(f"Git checkpoint does not resolve to a commit: {reference}")
    return findings


def _git_text(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Git command failed")
    return result.stdout.strip()


def _repository_baseline(root: Path) -> dict[str, str]:
    head = _git_text(root, "rev-parse", "HEAD")
    return {
        "model": f"sha256:{authority_digest(root)}",
        "implementation": f"git:{head}",
        "language": f"sha256:{_sha256(root / 'model' / 'config' / 'language.lock.json')}",
        "execution_environment": f"sha256:{_sha256(root / 'uv.lock')}",
        "checkpoint": f"git:{head}",
    }


def _repository_baseline_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    findings: list[str] = []
    actual = _repository_baseline(root)
    observed = record["baselines"]["observed"]
    for dimension in ("model", "language", "execution_environment"):
        identity = actual[dimension]
        if observed[dimension] != identity:
            findings.append(f"observed {dimension} baseline does not match the current repository")
    if record["evolution"]["lifecycle"] != "complete":
        for dimension in ("implementation", "checkpoint"):
            if observed[dimension] != actual[dimension]:
                findings.append(
                    f"observed {dimension} baseline does not match the current repository"
                )
        return findings

    target = record["baselines"]["target"]
    if target is None:
        return findings
    if not target["implementation"].startswith("git:"):
        findings.append("complete target implementation is not a Vellis Git checkpoint")
        return findings
    target_revision = target["implementation"].removeprefix("git:")
    head_revision = actual["implementation"].removeprefix("git:")
    if target_revision != head_revision:
        try:
            changed = _git_text(
                root, "diff", "--name-only", target_revision, head_revision
            ).splitlines()
        except RuntimeError:
            changed = []
        if changed != ["system-evolution.yaml"]:
            findings.append(
                "complete target implementation is not the reviewed repository checkpoint"
            )
    dirty = [
        line
        for line in _git_text(root, "status", "--porcelain", "--untracked-files=no").splitlines()
        if not line.endswith(" system-evolution.yaml")
    ]
    if dirty:
        findings.append("complete evolution has dirty tracked state outside its record")
    return findings


def _approval_checkpoint_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    findings: list[str] = []
    approvals = [("evolution", record["evolution"]["approval"])] + [
        (f"work item {item['id']}", item["approval"]) for item in record["work_items"]
    ]
    for label, approval in approvals:
        if approval["status"] != "accepted":
            continue
        checkpoint = approval["checkpoint"]
        if not isinstance(checkpoint, str) or not checkpoint.startswith("git:"):
            findings.append(f"accepted {label} approval is not bound to a Vellis Git checkpoint")
            continue
        revision = checkpoint.removeprefix("git:")
        try:
            source = _git_text(root, "show", f"{revision}:system-evolution.yaml")
            historical = yaml.load(source, Loader=UniqueKeyLoader)  # noqa: S506
        except RuntimeError, yaml.YAMLError:
            findings.append(f"accepted {label} approval checkpoint is not reconstructible")
            continue
        if not isinstance(historical, dict):
            findings.append(f"accepted {label} approval checkpoint has no evolution record")
            continue
        if label == "evolution":
            historical_approval = historical.get("evolution", {}).get("approval", {})
        else:
            item_id = label.removeprefix("work item ")
            historical_item = next(
                (item for item in historical.get("work_items", []) if item.get("id") == item_id),
                {},
            )
            historical_approval = historical_item.get("approval", {})
        if historical_approval.get("status") != "accepted":
            findings.append(f"accepted {label} approval is absent from its checkpoint")
    return findings


def validate_record(record: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    errors = sorted(
        Draft202012Validator(
            _schema(root / SYSTEM_EVOLUTION_SCHEMA_PATH.relative_to(ROOT))
        ).iter_errors(record),
        key=lambda error: list(error.absolute_path),
    )
    findings = [f"{_json_path(error.absolute_path)}: {error.message}" for error in errors]
    if errors:
        return findings

    finding_ids = [entry["id"] for entry in record["findings"]]
    decision_ids = [entry["id"] for entry in record["decisions"]]
    work_ids = [entry["id"] for entry in record["work_items"]]
    for label, identifiers in (
        ("finding", finding_ids),
        ("decision", decision_ids),
        ("work item", work_ids),
    ):
        for duplicate in _duplicates(identifiers):
            findings.append(f"duplicate {label} ID: {duplicate}")
    finding_by_id = {entry["id"]: entry for entry in record["findings"]}
    decision_by_id = {entry["id"]: entry for entry in record["decisions"]}
    work_by_id = {entry["id"]: entry for entry in record["work_items"]}
    closed_dispositions = {"resolved", "accepted", "out-of-scope"}
    all_ids = [*finding_by_id, *decision_by_id, *work_by_id]
    for duplicate in _duplicates(all_ids):
        findings.append(f"ID {duplicate} is reused across the evolution record")
    for duplicate in _duplicates([str(item["order"]) for item in work_by_id.values()]):
        findings.append(f"duplicate work-item order: {duplicate}")

    for item in work_by_id.values():
        for dependency in item["dependencies"]:
            if dependency not in work_by_id:
                findings.append(f"{item['id']} depends on unknown work item {dependency}")
            elif work_by_id[dependency]["order"] >= item["order"]:
                findings.append(f"{item['id']} dependency {dependency} must have a lower order")
        for finding_id in item["finding_ids"]:
            if finding_id not in finding_by_id:
                findings.append(f"{item['id']} owns unknown finding {finding_id}")
        for decision_id in item["decision_ids"]:
            if decision_id not in decision_by_id:
                findings.append(f"{item['id']} owns unknown decision {decision_id}")
        for contribution in item["authority"]:
            unknown_remaining = set(contribution["remaining_work_item_ids"]) - set(work_by_id)
            for remaining_id in sorted(unknown_remaining):
                findings.append(
                    f"{item['id']} authority names unknown remaining work item {remaining_id}"
                )
            if contribution["coverage"] == "full" and contribution["remaining_work_item_ids"]:
                findings.append(f"{item['id']} claims full authority with remaining work")
            if (
                contribution["coverage"] == "partial"
                and not contribution["remaining_work_item_ids"]
            ):
                findings.append(f"{item['id']} claims partial authority without remaining work")
    findings.extend(_cycle_findings(work_by_id))

    for finding in finding_by_id.values():
        owner = finding["owner_work_item_id"]
        if owner not in work_by_id:
            findings.append(f"finding {finding['id']} names unknown owner {owner}")
        elif finding["id"] not in work_by_id[owner]["finding_ids"]:
            findings.append(f"finding {finding['id']} is not listed by owner {owner}")
        listed_by = [
            item["id"] for item in work_by_id.values() if finding["id"] in item["finding_ids"]
        ]
        if listed_by != [owner]:
            findings.append(
                f"finding {finding['id']} is listed by {listed_by}, expected [{owner!r}]"
            )
        if finding["disposition"] == "resolved":
            if finding["implementation_status"] not in {"conforming", "not applicable"}:
                findings.append(
                    f"resolved finding {finding['id']} has implementation status "
                    f"{finding['implementation_status']}"
                )
            if not finding["evidence_refs"]:
                findings.append(f"resolved finding {finding['id']} has no evidence")
        if finding["disposition"] == "accepted" and not finding["evidence_refs"]:
            findings.append(f"accepted finding {finding['id']} has no acceptance evidence")

    for decision in decision_by_id.values():
        owner = decision["owner_work_item_id"]
        if owner not in work_by_id:
            findings.append(f"decision {decision['id']} names unknown owner {owner}")
        elif decision["id"] not in work_by_id[owner]["decision_ids"]:
            findings.append(f"decision {decision['id']} is not listed by owner {owner}")
        listed_by = [
            item["id"] for item in work_by_id.values() if decision["id"] in item["decision_ids"]
        ]
        if listed_by != [owner]:
            findings.append(
                f"decision {decision['id']} is listed by {listed_by}, expected [{owner!r}]"
            )
        if decision["implementation_status"] == "conforming" and not decision["evidence_refs"]:
            findings.append(f"conforming decision {decision['id']} has no evidence")

    baselines = record["baselines"]
    expected = baselines["target"] or baselines["source"]
    baseline_fields = (
        "model",
        "implementation",
        "language",
        "execution_environment",
        "checkpoint",
    )
    baseline_matches = all(
        expected[field] == baselines["observed"][field] for field in baseline_fields
    )
    if baselines["status"] == "current" and not baseline_matches:
        findings.append("current baselines must match the observed target or source baseline")
    if baselines["status"] == "stale" and baseline_matches:
        findings.append("stale baselines must differ from the observed target or source baseline")
    for item in work_by_id.values():
        binding = item["planned_baseline"]
        if (
            item["lifecycle"] in {"ready", "active"}
            and binding["identity"] != baselines["observed"][binding["dimension"]]
        ):
            findings.append(
                f"{item['lifecycle']} work item {item['id']} has stale planned baseline"
                f" {binding['dimension']}={binding['identity']}"
            )
        if (
            item["lifecycle"] == "complete"
            and binding["identity"]
            not in {
                baseline[binding["dimension"]]
                for baseline in (baselines["source"], baselines["target"], baselines["observed"])
                if baseline is not None
            }
            and not binding["identity"].startswith("git:")
        ):
            findings.append(
                f"complete work item {item['id']} has an unrecognized historical planned baseline"
            )

    active = [item for item in work_by_id.values() if item["lifecycle"] == "active"]
    if len(active) > 1:
        findings.append("more than one work item is active")
    for item in work_by_id.values():
        if item["lifecycle"] not in {"ready", "active", "complete"}:
            continue
        incomplete = [
            dependency
            for dependency in item["dependencies"]
            if dependency in work_by_id and work_by_id[dependency]["lifecycle"] != "complete"
        ]
        if incomplete:
            findings.append(
                f"{item['lifecycle']} work item {item['id']} has incomplete dependencies"
                f" {incomplete}"
            )

    lifecycle = record["evolution"]["lifecycle"]
    if active and lifecycle != "active":
        findings.append("an active work item requires an active evolution")
    if lifecycle == "active" and len(active) != 1:
        findings.append("an active evolution requires exactly one active work item")
    ready = [item for item in work_by_id.values() if item["lifecycle"] == "ready"]
    if lifecycle == "ready" and not ready:
        findings.append("a ready evolution requires at least one ready work item")
    if ready and lifecycle != "ready":
        findings.append("a ready work item requires a ready evolution")
    if lifecycle in {"discovery", "planning", "awaiting-approval"} and (active or ready):
        findings.append(f"a {lifecycle} evolution cannot contain executable work")
    pending_approvals = [
        item for item in work_by_id.values() if item["approval"]["status"] == "pending"
    ]
    if lifecycle == "awaiting-approval" and not pending_approvals:
        findings.append("an awaiting-approval evolution requires a pending work-item approval")
    for item in work_by_id.values():
        approval = item["approval"]["status"]
        if item["lifecycle"] in {"ready", "active", "complete"} and approval not in {
            "accepted",
            "not-required",
        }:
            findings.append(
                f"{item['lifecycle']} work item {item['id']} has unsatisfied approval {approval}"
            )
        if approval == "accepted" and item["approval"]["checkpoint"] is None:
            findings.append(f"accepted approval for {item['id']} has no attributable checkpoint")
        if item["blocker"] is not None and item["lifecycle"] != "blocked":
            findings.append(f"work item {item['id']} has a blocker but is not blocked")
        if item["lifecycle"] == "blocked" and item["blocker"] is None:
            findings.append(f"blocked work item {item['id']} has no blocker")
        if item["lifecycle"] == "stale" and item["blocker"] is None:
            findings.append(f"stale work item {item['id']} has no blocker")
    evolution_blocker = record["evolution"]["blocker"]
    if (
        record["evolution"]["approval"]["status"] == "accepted"
        and record["evolution"]["approval"]["checkpoint"] is None
    ):
        findings.append("accepted evolution approval has no attributable checkpoint")
    if evolution_blocker is not None and lifecycle not in {"blocked", "stale"}:
        findings.append("an evolution blocker requires a blocked or stale lifecycle")
    if (
        lifecycle == "blocked"
        and evolution_blocker is None
        and not any(item["blocker"] is not None for item in work_by_id.values())
    ):
        findings.append("blocked evolution has no blocker")
    for label, blocker in (
        ("evolution", evolution_blocker),
        *((f"work item {item['id']}", item["blocker"]) for item in work_by_id.values()),
    ):
        if blocker is None:
            continue
        for finding_id in blocker["finding_ids"]:
            if finding_id not in finding_by_id:
                findings.append(f"{label} blocker names unknown finding {finding_id}")
    if lifecycle == "stale" and record["baselines"]["status"] != "stale":
        findings.append("stale lifecycle requires stale baselines")
    if record["baselines"]["status"] == "stale" and lifecycle not in {"stale", "blocked"}:
        findings.append("stale baselines require stale or blocked lifecycle")

    for item in work_by_id.values():
        if item["lifecycle"] != "complete":
            continue
        if item["checkpoint"] is None:
            findings.append(f"complete work item {item['id']} has no checkpoint")
        if not item["evidence_refs"]:
            findings.append(f"complete work item {item['id']} has no evidence")
        if item["blocker"] is not None:
            findings.append(f"complete work item {item['id']} retains a blocker")
        if item["implementation_status"] not in {"conforming", "not applicable"}:
            findings.append(
                f"complete work item {item['id']} has implementation status "
                f"{item['implementation_status']}"
            )
        open_owned = [
            finding_id
            for finding_id in item["finding_ids"]
            if finding_id in finding_by_id
            and finding_by_id[finding_id]["disposition"] not in closed_dispositions
        ]
        if open_owned:
            findings.append(f"complete work item {item['id']} has open findings {open_owned}")
        incomplete_decisions = [
            decision_id
            for decision_id in item["decision_ids"]
            if decision_id in decision_by_id
            and decision_by_id[decision_id]["implementation_status"]
            not in {"conforming", "not applicable"}
        ]
        if incomplete_decisions:
            findings.append(
                f"complete work item {item['id']} has incomplete decisions {incomplete_decisions}"
            )

    if lifecycle == "complete":
        if any(item["lifecycle"] != "complete" for item in work_by_id.values()):
            findings.append("complete evolution has incomplete work items")
        if record["closure"]["finding_disposition"] != "complete":
            findings.append("complete evolution has open finding disposition")
        if record["closure"]["checkpoint"] is None:
            findings.append("complete evolution has no closure checkpoint")
        if record["evolution"]["checkpoint"] is None:
            findings.append("complete evolution has no evolution checkpoint")
        elif record["evolution"]["checkpoint"] != record["closure"]["checkpoint"]:
            findings.append("complete evolution and closure checkpoints must match")
        if record["evolution"]["approval"]["status"] not in {"accepted", "not-required"}:
            findings.append("complete evolution has an unsatisfied approval roll-up")
        if record["evolution"]["blocker"] is not None:
            findings.append("complete evolution retains a blocker")
        if baselines["status"] != "current" or baselines["target"] is None:
            findings.append("complete evolution requires a current target baseline")
        open_findings = [
            finding["id"]
            for finding in finding_by_id.values()
            if finding["disposition"] not in closed_dispositions
        ]
        if open_findings:
            findings.append(f"complete evolution has open findings {open_findings}")
        incomplete_decisions = [
            decision["id"]
            for decision in decision_by_id.values()
            if decision["implementation_status"] not in {"conforming", "not applicable"}
        ]
        if incomplete_decisions:
            findings.append(f"complete evolution has incomplete decisions {incomplete_decisions}")
        closure = record["closure"]
        if closure["model_status"] not in {"accepted", "unchanged"}:
            findings.append("complete evolution requires accepted or unchanged model status")
        for dimension in ("implementation_status", "integration_status", "external_status"):
            if closure[dimension] not in {"conforming", "not applicable"}:
                findings.append(
                    f"complete evolution requires conforming or not-applicable {dimension}"
                )
        if not closure["evidence_refs"]:
            findings.append("complete evolution has no closure evidence")
        required_lenses = set(record["scope"]["review_lenses"])
        review_counts = Counter(review["lens"] for review in closure["reviews"])
        duplicate_reviews = sorted(lens for lens, count in review_counts.items() if count > 1)
        if duplicate_reviews:
            findings.append(f"complete evolution has duplicate review lenses {duplicate_reviews}")
        undeclared_reviews = review_counts.keys() - required_lenses
        if undeclared_reviews:
            findings.append(
                f"complete evolution has undeclared review lenses {sorted(undeclared_reviews)}"
            )
        unresolved_reviews = sorted(
            review["lens"] for review in closure["reviews"] if review["status"] != "clean"
        )
        if unresolved_reviews:
            findings.append(f"complete evolution has unresolved reviews {unresolved_reviews}")
        clean_reviews = {
            review["lens"]: review for review in closure["reviews"] if review["status"] == "clean"
        }
        missing_lenses = required_lenses - clean_reviews.keys()
        if missing_lenses:
            findings.append(
                f"complete evolution lacks clean required review lenses {sorted(missing_lenses)}"
            )
        for lens in required_lenses & clean_reviews.keys():
            review = clean_reviews[lens]
            if not review["evidence_refs"]:
                findings.append(f"clean required review {lens!r} has no attributable evidence")
            if review["reviewer"] is None or review["checkpoint"] is None:
                findings.append(f"clean required review {lens!r} lacks reviewer attribution")

    for review in record["closure"]["reviews"]:
        attributed = review["reviewer"] is not None and review["checkpoint"] is not None
        if review["status"] in {"findings", "clean"} and not attributed:
            findings.append(f"review {review['lens']!r} lacks reviewer attribution")
        if review["status"] in {"findings", "clean"} and not review["evidence_refs"]:
            findings.append(f"review {review['lens']!r} has no attributable evidence")
        if review["status"] == "pending" and (attributed or review["evidence_refs"]):
            findings.append(f"pending review {review['lens']!r} retains completed-review state")

    findings.extend(_reference_findings(record, root=root))
    findings.extend(_git_checkpoint_findings(record, root=root))
    findings.extend(_repository_baseline_findings(record, root=root))
    findings.extend(_approval_checkpoint_findings(record, root=root))
    return findings


def status(record: dict[str, Any]) -> str:
    ordered = sorted(record["work_items"], key=lambda item: item["order"])
    active = next((item["id"] for item in ordered if item["lifecycle"] == "active"), None)
    complete = {item["id"] for item in ordered if item["lifecycle"] == "complete"}
    ready = [
        item["id"]
        for item in ordered
        if item["lifecycle"] == "ready" and set(item["dependencies"]).issubset(complete)
    ]
    approval = record["evolution"]["approval"]["status"]
    next_work = active or (ready[0] if ready else "none")
    closed_dispositions = {"resolved", "accepted", "out-of-scope"}
    open_findings = sum(
        finding["disposition"] not in closed_dispositions for finding in record["findings"]
    )
    return "\n".join(
        (
            f"evolution: {record['evolution']['id']}",
            f"lifecycle: {record['evolution']['lifecycle']}",
            f"approval: {approval}",
            f"next_work: {next_work}",
            f"open_findings: {open_findings}",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect system evolution records.")
    parser.add_argument("command", choices=("check", "status"))
    parser.add_argument("--record", type=Path, default=SYSTEM_EVOLUTION_PATH)
    args = parser.parse_args()
    record = load_record(args.record)
    findings = validate_record(record, root=ROOT)
    if findings:
        print("\n".join(findings))
        return 1
    if args.command == "status":
        print(status(record))
    else:
        print(f"Validated evolution record {record['evolution']['id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
