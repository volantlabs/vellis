from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator

try:
    from . import sysml_validator
    from .model_layout import (
        IMPLEMENTATION_CAMPAIGN_PATH,
        IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH,
        ROOT,
    )
except ImportError:  # pragma: no cover - direct script execution
    import sysml_validator  # type: ignore[no-redef]
    from model_layout import (  # type: ignore[no-redef]
        IMPLEMENTATION_CAMPAIGN_PATH,
        IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH,
        ROOT,
    )


APPROVAL_CHECKPOINT = re.compile(r"approval:(?P<plan>[0-9a-f]{40})\Z")
SLICE_CHECKPOINT = re.compile(
    r"slice:(?P<slice>S[0-9]{3}):(?P<plan>[0-9a-f]{12}):(?P<attempt>[1-9][0-9]*)\Z"
)
CLOSURE_CHECKPOINT = re.compile(r"closure:(?P<plan>[0-9a-f]{12}):(?P<attempt>[1-9][0-9]*)\Z")


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def authored_model_files(root: Path = ROOT) -> list[Path]:
    files = sorted((root / "model").glob("*.sysml"), key=lambda path: path.name)
    if not files:
        raise ValueError(f"no authored SysML files found under {root / 'model'}")
    return files


def authority_digest(root: Path = ROOT) -> str:
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
        }
        for path in authored_model_files(root)
    ]
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def observed_baseline(root: Path = ROOT) -> dict[str, str]:
    return {
        "authority_sha256": authority_digest(root),
        "language_sha256": _sha256(root / "model" / "config" / "language.lock.json"),
        "validator_sha256": _sha256(root / "model" / "config" / "validator.lock.json"),
    }


def load_campaign(path: Path = IMPLEMENTATION_CAMPAIGN_PATH) -> dict[str, Any]:
    return load_campaign_text(path.read_text(encoding="utf-8"), label=str(path))


def load_campaign_text(source: str, *, label: str = "campaign") -> dict[str, Any]:
    value = yaml.load(source, Loader=UniqueKeyLoader)  # noqa: S506
    if not isinstance(value, dict):
        raise ValueError(f"{label}: campaign must be a YAML mapping")
    return cast(dict[str, Any], value)


def _schema(path: Path = IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: schema must be a JSON object")
    Draft202012Validator.check_schema(value)
    return cast(dict[str, Any], value)


def _json_path(parts: Any) -> str:
    return ".".join(str(part) for part in parts) or "campaign"


def _duplicates(values: list[Any]) -> list[Any]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _cycle_findings(slices: dict[str, dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(slice_id: str, trail: list[str]) -> None:
        if slice_id in visited:
            return
        if slice_id in visiting:
            start = trail.index(slice_id)
            findings.append("slice dependency cycle: " + " -> ".join([*trail[start:], slice_id]))
            return
        visiting.add(slice_id)
        trail.append(slice_id)
        for dependency in slices[slice_id]["dependencies"]:
            if dependency in slices:
                visit(dependency, trail)
        trail.pop()
        visiting.remove(slice_id)
        visited.add(slice_id)

    for slice_id in slices:
        visit(slice_id, [])
    return findings


def _evidence_reference_findings(reference: str, *, label: str, root: Path) -> list[str]:
    if reference.startswith("command:"):
        command = reference.removeprefix("command:")
        if not command.strip() or command != command.strip() or "\n" in command:
            return [f"{label} command evidence must contain one exact nonempty command"]
        return []
    if reference.startswith("path:"):
        value = reference.removeprefix("path:")
        path_text, separator, fragment = value.partition("#")
        path = PurePosixPath(path_text)
        if (
            separator != "#"
            or not fragment.strip()
            or not path_text
            or "\\" in path_text
            or path.is_absolute()
            or ".." in path.parts
        ):
            return [f"{label} path evidence must be path:<repo-relative-path>#<test-or-section>"]
        if not (root / Path(*path.parts)).exists():
            return [f"{label} path evidence does not exist: {path_text}"]
        return []
    return [f"{label} evidence must use path: or command:"]


def _all_evidence_references(campaign: dict[str, Any]) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    blocker = campaign["campaign"]["blocker"]
    if blocker is not None:
        references.extend(
            (f"campaign.blocker.evidence_refs[{index}]", reference)
            for index, reference in enumerate(blocker["evidence_refs"])
        )
    for authority in campaign["authority"]:
        references.extend(
            (f"authority.{authority['id']}.evidence_refs[{index}]", reference)
            for index, reference in enumerate(authority["evidence_refs"])
        )
    for entry in campaign["slices"]:
        references.extend(
            (f"slice.{entry['id']}.evidence_refs[{index}]", reference)
            for index, reference in enumerate(entry["evidence_refs"])
        )
        if entry["blocker"] is not None:
            references.extend(
                (f"slice.{entry['id']}.blocker.evidence_refs[{index}]", reference)
                for index, reference in enumerate(entry["blocker"]["evidence_refs"])
            )
    references.extend(
        (f"closure.evidence_refs[{index}]", reference)
        for index, reference in enumerate(campaign["closure"]["evidence_refs"])
    )
    return references


def _checkpoint_format_findings(campaign: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    approval = campaign["campaign"]["plan_approval"]
    approval_checkpoint = approval["checkpoint"]
    approval_match = (
        APPROVAL_CHECKPOINT.fullmatch(approval_checkpoint)
        if approval_checkpoint is not None
        else None
    )
    if approval_checkpoint is not None and approval_match is None:
        findings.append("plan approval checkpoint must be approval:<full-plan-commit-sha>")
    if approval["status"] != "accepted" and approval_checkpoint is not None:
        findings.append("a non-accepted plan may not retain an approval checkpoint")

    completed_entries: list[dict[str, Any]] = []
    for entry in campaign["slices"]:
        checkpoint = entry["checkpoint"]
        match = SLICE_CHECKPOINT.fullmatch(checkpoint) if checkpoint is not None else None
        if checkpoint is not None and match is None:
            findings.append(
                f"slice {entry['id']} checkpoint must be "
                "slice:<slice-id>:<approved-plan-short-sha>:<attempt>"
            )
        elif match is not None and match.group("slice") != entry["id"]:
            findings.append(f"slice {entry['id']} checkpoint names {match.group('slice')}")
        if entry["lifecycle"] == "active" and checkpoint is not None:
            findings.append(f"active slice {entry['id']} must retain no checkpoint before commit")
        if entry["lifecycle"] == "complete" and checkpoint is not None:
            completed_entries.append(entry)

    closure_checkpoint = campaign["closure"]["checkpoint"]
    if closure_checkpoint is not None and CLOSURE_CHECKPOINT.fullmatch(closure_checkpoint) is None:
        findings.append("closure checkpoint must be closure:<approved-plan-short-sha>:<attempt>")

    approved_plan = approval_match.group("plan") if approval_match is not None else None
    if approved_plan is not None:
        for entry in campaign["slices"]:
            checkpoint = entry["checkpoint"]
            match = SLICE_CHECKPOINT.fullmatch(checkpoint) if checkpoint is not None else None
            if match is not None and match.group("plan") != approved_plan[:12]:
                findings.append(
                    f"slice {entry['id']} checkpoint does not use the approved plan commit"
                )
        match = (
            CLOSURE_CHECKPOINT.fullmatch(closure_checkpoint)
            if closure_checkpoint is not None
            else None
        )
        if match is not None and match.group("plan") != approved_plan[:12]:
            findings.append("closure checkpoint does not use the approved plan commit")

    campaign_checkpoint = campaign["campaign"]["checkpoint"]
    if campaign_checkpoint is not None and not any(
        pattern.fullmatch(campaign_checkpoint)
        for pattern in (APPROVAL_CHECKPOINT, SLICE_CHECKPOINT, CLOSURE_CHECKPOINT)
    ):
        findings.append("campaign checkpoint has an unsupported project checkpoint format")
    if campaign["campaign"]["lifecycle"] in {"ready", "active"}:
        if campaign_checkpoint is None:
            findings.append("an executable campaign requires a recoverable campaign checkpoint")
        latest_completed = max(completed_entries, key=lambda entry: entry["order"], default=None)
        expected_checkpoint = (
            latest_completed["checkpoint"] if latest_completed is not None else approval_checkpoint
        )
        if campaign_checkpoint != expected_checkpoint:
            findings.append(
                "a ready or active campaign checkpoint must be the latest recoverable checkpoint"
            )
    if campaign["campaign"]["lifecycle"] == "complete":
        if campaign_checkpoint != closure_checkpoint:
            findings.append("a complete campaign must use its closure checkpoint")
    return findings


def validate_campaign(
    campaign: dict[str, Any],
    *,
    root: Path = ROOT,
    schema_path: Path = IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH,
) -> list[str]:
    validator = Draft202012Validator(_schema(schema_path))
    findings = [
        f"{_json_path(error.absolute_path)}: {error.message}"
        for error in sorted(
            validator.iter_errors(campaign), key=lambda item: list(item.absolute_path)
        )
    ]
    if findings:
        return findings

    for label, reference in _all_evidence_references(campaign):
        findings.extend(_evidence_reference_findings(reference, label=label, root=root))
    findings.extend(_checkpoint_format_findings(campaign))

    baseline = campaign["model_baseline"]
    expected_files = [path.relative_to(root).as_posix() for path in authored_model_files(root)]
    if baseline["authority_files"] != expected_files:
        findings.append("model_baseline.authority_files must equal the sorted authored model files")

    actual = observed_baseline(root)
    observed = baseline["observed"]
    for key, value in actual.items():
        if observed[key] != value:
            findings.append(f"model_baseline.observed.{key} does not match the current repository")

    baseline_keys = ("authority_sha256", "language_sha256", "validator_sha256")
    baseline_matches = all(baseline["planned"][key] == observed[key] for key in baseline_keys)
    if baseline["status"] == "current" and not baseline_matches:
        findings.append("a current model baseline must have matching planned and observed digests")
    if baseline["status"] == "stale" and baseline_matches:
        findings.append("a stale model baseline must differ from its observed baseline")

    authorities = campaign["authority"]
    authority_ids = [entry["id"] for entry in authorities]
    for duplicate in _duplicates(authority_ids):
        findings.append(f"duplicate authority id: {duplicate}")
    authority_by_id = {entry["id"]: entry for entry in authorities}
    authority_files = set(baseline["authority_files"])
    for entry in authorities:
        refs = [reference["model_ref"] for reference in entry["refs"]]
        for duplicate in _duplicates(refs):
            findings.append(f"authority {entry['id']} repeats model reference {duplicate}")
        for reference in entry["refs"]:
            if reference["source"] not in authority_files:
                findings.append(
                    f"authority {entry['id']} source is outside the authored model scope"
                )

    slice_entries = campaign["slices"]
    slice_ids = [entry["id"] for entry in slice_entries]
    orders = [entry["order"] for entry in slice_entries]
    for duplicate in _duplicates(slice_ids):
        findings.append(f"duplicate slice id: {duplicate}")
    for duplicate in _duplicates(orders):
        findings.append(f"duplicate slice order: {duplicate}")
    slices = {entry["id"]: entry for entry in slice_entries}
    decision_ids = [
        decision["id"] for entry in slice_entries for decision in entry["realization_decisions"]
    ]
    for duplicate in _duplicates(decision_ids):
        findings.append(f"duplicate realization decision id: {duplicate}")

    for entry in slice_entries:
        slice_id = entry["id"]
        unknown_dependencies = set(entry["dependencies"]) - set(slices)
        for dependency in sorted(unknown_dependencies):
            findings.append(f"slice {slice_id} has unknown dependency {dependency}")
        if slice_id in entry["dependencies"]:
            findings.append(f"slice {slice_id} depends on itself")
        for dependency in entry["dependencies"]:
            if dependency in slices and slices[dependency]["order"] >= entry["order"]:
                findings.append(f"slice {slice_id} dependency {dependency} must have a lower order")

        contribution_ids = [item["authority_id"] for item in entry["authority"]]
        for duplicate in _duplicates(contribution_ids):
            findings.append(f"slice {slice_id} repeats authority contribution {duplicate}")
        for contribution in entry["authority"]:
            authority_id = contribution["authority_id"]
            if authority_id not in authority_by_id:
                findings.append(f"slice {slice_id} has unknown authority {authority_id}")
            remaining = contribution["remaining_slice_ids"]
            if contribution["coverage"] == "full" and remaining:
                findings.append(
                    f"slice {slice_id} full contribution {authority_id} has a remainder"
                )
            if contribution["coverage"] == "partial" and not remaining:
                findings.append(
                    f"slice {slice_id} partial contribution {authority_id} has no remainder"
                )
            if authority_id in authority_by_id:
                expected_remainder = set(authority_by_id[authority_id]["slice_ids"]) - {slice_id}
                if contribution["coverage"] == "partial" and set(remaining) != expected_remainder:
                    findings.append(
                        f"slice {slice_id} partial contribution {authority_id} must name every "
                        "other aggregate contributor"
                    )
                if contribution["coverage"] == "full" and expected_remainder:
                    findings.append(
                        f"slice {slice_id} full contribution {authority_id} must be self-sufficient"
                    )
            for remaining_id in remaining:
                if remaining_id not in slices:
                    findings.append(
                        f"slice {slice_id} contribution {authority_id} has unknown "
                        f"remainder {remaining_id}"
                    )
                elif remaining_id == slice_id:
                    findings.append(
                        f"slice {slice_id} contribution {authority_id} lists itself as a remainder"
                    )
                elif (
                    authority_id in authority_by_id
                    and remaining_id not in authority_by_id[authority_id]["slice_ids"]
                ):
                    findings.append(
                        f"slice {slice_id} contribution {authority_id} remainder {remaining_id} "
                        "is not an aggregate contributor"
                    )

        blocker = entry["blocker"]
        if entry["lifecycle"] == "blocked" and blocker is None:
            findings.append(f"blocked slice {slice_id} must record a blocker")
        if blocker is not None and entry["lifecycle"] not in {"blocked", "stale"}:
            findings.append(f"slice {slice_id} has a blocker but is not blocked or stale")
        if blocker is not None:
            for authority_id in blocker["authority_ids"]:
                if authority_id not in authority_by_id:
                    findings.append(
                        f"slice {slice_id} blocker has unknown authority {authority_id}"
                    )

        for decision in entry["realization_decisions"]:
            for authority_id in decision["authority_ids"]:
                if authority_id not in authority_by_id:
                    findings.append(
                        f"slice {slice_id} decision has unknown authority {authority_id}"
                    )

    findings.extend(_cycle_findings(slices))

    for authority in authorities:
        authority_id = authority["id"]
        unknown_slices = set(authority["slice_ids"]) - set(slices)
        for slice_id in sorted(unknown_slices):
            findings.append(f"authority {authority_id} has unknown slice {slice_id}")
        contributed_by = {
            entry["id"]
            for entry in slice_entries
            if authority_id in {item["authority_id"] for item in entry["authority"]}
        }
        if contributed_by != set(authority["slice_ids"]):
            findings.append(f"authority {authority_id} slice links are not bidirectional")

    active = [entry for entry in slice_entries if entry["lifecycle"] == "active"]
    if len(active) > 1:
        findings.append("at most one slice may be active")

    approval = campaign["campaign"]["plan_approval"]
    campaign_lifecycle = campaign["campaign"]["lifecycle"]
    execution_states = {"ready", "active", "complete"}
    if approval["status"] != "accepted":
        if any(entry["lifecycle"] in execution_states for entry in slice_entries):
            findings.append("unapproved plans may not have ready, active, or complete slices")
        if campaign_lifecycle in execution_states:
            findings.append("an unapproved campaign may not be ready, active, or complete")
    if approval["status"] == "accepted" and approval["checkpoint"] is None:
        findings.append("accepted plan approval requires a checkpoint")

    if campaign_lifecycle == "active" and len(active) != 1:
        findings.append("an active campaign must have exactly one active slice")
    if active and campaign_lifecycle != "active":
        findings.append("an active slice requires an active campaign")
    if campaign_lifecycle == "ready":
        ready = [entry for entry in slice_entries if entry["lifecycle"] == "ready"]
        incomplete = [entry for entry in slice_entries if entry["lifecycle"] != "complete"]
        if incomplete and len(ready) != 1:
            findings.append("a ready campaign must have exactly one ready slice")
        eligible = [
            entry
            for entry in incomplete
            if entry["lifecycle"] in {"pending", "ready"}
            and all(
                slices[dependency]["lifecycle"] == "complete"
                for dependency in entry["dependencies"]
            )
        ]
        if ready and eligible:
            expected = min(eligible, key=lambda entry: entry["order"])
            if ready[0]["id"] != expected["id"]:
                findings.append(
                    f"ready slice {ready[0]['id']} is not the lowest-ordered dependency-ready "
                    f"slice {expected['id']}"
                )

    campaign_blocker = campaign["campaign"]["blocker"]
    if (
        campaign_lifecycle == "blocked"
        and campaign_blocker is None
        and not any(entry["lifecycle"] == "blocked" for entry in slice_entries)
    ):
        findings.append("a blocked campaign must record a campaign or slice blocker")
    if campaign_blocker is not None:
        for authority_id in campaign_blocker["authority_ids"]:
            if authority_id not in authority_by_id:
                findings.append(f"campaign blocker has unknown authority {authority_id}")

    if baseline["status"] == "stale":
        if campaign_lifecycle != "stale":
            findings.append("a stale model baseline requires a stale campaign")
        if approval["status"] != "changes-required":
            findings.append("a stale model baseline invalidates plan approval")
        if active:
            findings.append("a stale campaign may not have an active slice")
        if campaign_blocker is None or campaign_blocker["classification"] != "stale baseline":
            findings.append("a stale campaign must record a stale baseline blocker")
    elif campaign_lifecycle == "stale":
        findings.append("a stale campaign requires a stale model baseline")

    for entry in slice_entries:
        slice_id = entry["id"]
        if entry["lifecycle"] in {"ready", "active", "complete"}:
            incomplete = [
                dependency
                for dependency in entry["dependencies"]
                if dependency in slices and slices[dependency]["lifecycle"] != "complete"
            ]
            if incomplete:
                findings.append(
                    f"slice {slice_id} is {entry['lifecycle']} with incomplete dependencies: "
                    + ", ".join(incomplete)
                )
        if entry["lifecycle"] == "complete":
            if entry["implementation_status"] != "conforming":
                findings.append(f"complete slice {slice_id} must be conforming")
            if not entry["evidence_refs"]:
                findings.append(f"complete slice {slice_id} requires evidence")
            if entry["checkpoint"] is None:
                findings.append(f"complete slice {slice_id} requires a checkpoint")
            if entry["blocker"] is not None:
                findings.append(f"complete slice {slice_id} may not have a blocker")

    planned_full = all(entry["planned_coverage"] == "full" for entry in authorities)
    closure = campaign["closure"]
    expected_closure_coverage = "full" if planned_full else "partial"
    if closure["authority_coverage"] != expected_closure_coverage:
        findings.append(
            "closure.authority_coverage must reflect aggregate authority planned coverage"
        )

    if campaign_lifecycle == "complete":
        if baseline["status"] != "current":
            findings.append("a complete campaign requires a current baseline")
        if approval["status"] != "accepted":
            findings.append("a complete campaign requires accepted plan approval")
        if campaign["campaign"]["blocker"] is not None:
            findings.append("a complete campaign may not have a blocker")
        if campaign["campaign"]["checkpoint"] is None:
            findings.append("a complete campaign requires a checkpoint")
        if not all(entry["lifecycle"] == "complete" for entry in slice_entries):
            findings.append("a complete campaign requires every slice complete")
        if not all(entry["implementation_status"] == "conforming" for entry in authorities):
            findings.append("a complete campaign requires every authority entry conforming")
        if closure["authority_coverage"] != "full":
            findings.append("a complete campaign requires full aggregate authority coverage")
        if closure["integration_status"] != "conforming":
            findings.append("a complete campaign requires conforming integration status")
        if closure["runnable_status"] != "conforming":
            findings.append("a complete campaign requires a conforming runnable boundary")
        if not closure["evidence_refs"]:
            findings.append("a complete campaign requires closure evidence")
        if closure["checkpoint"] is None:
            findings.append("a complete campaign requires a closure checkpoint")

    return findings


def qualified_model_reference_findings(campaign: dict[str, Any]) -> list[str]:
    authority_references = [
        reference["model_ref"]
        for authority in campaign["authority"]
        for reference in authority["refs"]
    ]
    verification_references = [
        reference for entry in campaign["slices"] for reference in entry["verification_refs"]
    ]
    references = [*authority_references, *verification_references]
    unresolved = sysml_validator.unresolved_model_references(references)
    return [f"qualified model reference does not resolve: {reference}" for reference in unresolved]


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def _checkpoint_ids(campaign: dict[str, Any]) -> set[str]:
    checkpoints = {
        campaign["campaign"]["plan_approval"]["checkpoint"],
        campaign["campaign"]["checkpoint"],
        campaign["closure"]["checkpoint"],
        *(entry["checkpoint"] for entry in campaign["slices"]),
    }
    return {checkpoint for checkpoint in checkpoints if checkpoint is not None}


def _commit_has_path(root: Path, commit: str, path: str) -> bool:
    completed = subprocess.run(  # noqa: S603
        ["git", "cat-file", "-e", f"{commit}:{path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _committed_evidence_findings(
    campaign: dict[str, Any], *, root: Path, commit: str, references: list[str]
) -> list[str]:
    findings: list[str] = []
    for reference in references:
        if not reference.startswith("path:"):
            continue
        path = reference.removeprefix("path:").partition("#")[0]
        if not _commit_has_path(root, commit, path):
            findings.append(f"checkpoint {commit} does not contain evidence path {path}")
    return findings


def checkpoint_binding_findings(campaign: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    checkpoints = _checkpoint_ids(campaign)
    if not checkpoints:
        return findings
    commit_bodies = {
        commit: _git(root, "show", "-s", "--format=%B", commit).splitlines()
        for commit in _git(root, "log", "HEAD", "--format=%H").splitlines()
    }
    for checkpoint in sorted(checkpoints):
        commits = [
            commit
            for commit, body_lines in commit_bodies.items()
            if f"Campaign-Checkpoint: {checkpoint}" in body_lines
        ]
        if len(commits) != 1:
            findings.append(
                f"checkpoint {checkpoint} must resolve to exactly one reachable commit; "
                f"found {len(commits)}"
            )
            continue

        commit = commits[0]
        body_lines = commit_bodies[commit]
        try:
            committed = load_campaign_text(
                _git(root, "show", f"{commit}:implementation-campaign.yaml"),
                label=f"{commit}:implementation-campaign.yaml",
            )
        except (RuntimeError, ValueError, yaml.YAMLError) as error:
            findings.append(f"checkpoint {checkpoint} has no readable committed campaign: {error}")
            continue

        approval_match = APPROVAL_CHECKPOINT.fullmatch(checkpoint)
        slice_match = SLICE_CHECKPOINT.fullmatch(checkpoint)
        closure_match = CLOSURE_CHECKPOINT.fullmatch(checkpoint)
        if approval_match is not None:
            parents = _git(root, "rev-list", "--parents", "-n", "1", commit).split()
            if len(parents) != 2 or parents[1] != approval_match.group("plan"):
                findings.append(
                    f"approval checkpoint {checkpoint} must be directly based on its plan commit"
                )
            if "Campaign-Approval: accepted" not in body_lines:
                findings.append(f"approval checkpoint {checkpoint} lacks its approval trailer")
            if committed["campaign"]["plan_approval"] != {
                "status": "accepted",
                "checkpoint": checkpoint,
            }:
                findings.append(
                    f"approval checkpoint {checkpoint} does not record accepted approval"
                )
            if committed["campaign"]["checkpoint"] != checkpoint:
                findings.append(f"approval checkpoint {checkpoint} is not the campaign checkpoint")
        elif slice_match is not None:
            slice_id = slice_match.group("slice")
            entry = next((item for item in committed["slices"] if item["id"] == slice_id), None)
            if "Campaign-Authority-Review: clean" not in body_lines:
                findings.append(f"slice checkpoint {checkpoint} lacks a clean authority review")
            if "Campaign-Engineering-Review: clean" not in body_lines:
                findings.append(f"slice checkpoint {checkpoint} lacks a clean engineering review")
            if (
                entry is None
                or entry["checkpoint"] != checkpoint
                or entry["lifecycle"] != "complete"
                or entry["implementation_status"] != "conforming"
                or not entry["evidence_refs"]
            ):
                findings.append(
                    f"slice checkpoint {checkpoint} does not contain a completed conforming "
                    "slice with evidence"
                )
            else:
                findings.extend(
                    _committed_evidence_findings(
                        committed,
                        root=root,
                        commit=commit,
                        references=entry["evidence_refs"],
                    )
                )
            if committed["campaign"]["checkpoint"] != checkpoint:
                findings.append(f"slice checkpoint {checkpoint} is not the campaign checkpoint")
        elif closure_match is not None:
            if "Campaign-Closure-Review: clean" not in body_lines:
                findings.append(f"closure checkpoint {checkpoint} lacks a clean closure review")
            closure = committed["closure"]
            if (
                committed["campaign"]["lifecycle"] != "complete"
                or committed["campaign"]["checkpoint"] != checkpoint
                or closure["checkpoint"] != checkpoint
                or not closure["evidence_refs"]
            ):
                findings.append(
                    f"closure checkpoint {checkpoint} does not contain completed campaign closure"
                )
            else:
                findings.extend(
                    _committed_evidence_findings(
                        committed,
                        root=root,
                        commit=commit,
                        references=closure["evidence_refs"],
                    )
                )
    return findings


def _status(campaign: dict[str, Any]) -> str:
    slice_entries = campaign["slices"]
    counts = Counter(entry["lifecycle"] for entry in slice_entries)
    active = next((entry for entry in slice_entries if entry["lifecycle"] == "active"), None)
    ready = sorted(
        (entry for entry in slice_entries if entry["lifecycle"] == "ready"),
        key=lambda entry: entry["order"],
    )
    blocker = campaign["campaign"]["blocker"]
    lines = [
        f"Campaign: {campaign['campaign']['id']}",
        f"Lifecycle: {campaign['campaign']['lifecycle']}",
        f"Baseline: {campaign['model_baseline']['status']}",
        f"Plan approval: {campaign['campaign']['plan_approval']['status']}",
        "Slices: " + ", ".join(f"{name}={counts[name]}" for name in sorted(counts)),
        f"Active: {active['id'] + ' ' + active['label'] if active else 'none'}",
        f"Next: {ready[0]['id'] + ' ' + ready[0]['label'] if ready else 'none'}",
        f"Blocker: {blocker['classification'] + ': ' + blocker['summary'] if blocker else 'none'}",
        (
            "Closure: authority="
            f"{campaign['closure']['authority_coverage']}, "
            f"integration={campaign['closure']['integration_status']}, "
            f"runnable={campaign['closure']['runnable_status']}"
        ),
        f"Checkpoint: {campaign['campaign']['checkpoint'] or 'none'}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect the implementation campaign")
    parser.add_argument("command", choices=("check", "status", "baseline", "checkpoint-check"))
    parser.add_argument(
        "--campaign",
        type=Path,
        default=IMPLEMENTATION_CAMPAIGN_PATH,
        help="campaign YAML path",
    )
    arguments = parser.parse_args()

    if arguments.command == "baseline":
        print(yaml.safe_dump(observed_baseline(), sort_keys=True).strip())
        return 0

    try:
        campaign = load_campaign(arguments.campaign)
        findings = validate_campaign(campaign)
        if not findings:
            findings.extend(qualified_model_reference_findings(campaign))
        if not findings and arguments.command == "checkpoint-check":
            findings.extend(checkpoint_binding_findings(campaign))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        print(f"ERROR {error}")
        return 1

    if findings:
        for finding in findings:
            print(f"ERROR {finding}")
        return 1
    if arguments.command == "status":
        print(_status(campaign))
    elif arguments.command == "checkpoint-check":
        print("Implementation campaign checkpoints resolve to committed project state.")
    else:
        print(
            f"Implementation campaign is valid for {len(campaign['authority'])} authority entries "
            f"and {len(campaign['slices'])} slices."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
