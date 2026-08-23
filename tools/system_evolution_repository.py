from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

import yaml

try:
    from .record_common import (
        UniqueKeyLoader,
        _evidence_reference_findings,
        _sha256,
        authority_digest,
    )
except ImportError:  # pragma: no cover - direct script execution
    from record_common import (  # type: ignore[no-redef]
        UniqueKeyLoader,
        _evidence_reference_findings,
        _sha256,
        authority_digest,
    )


def is_vellis_check_command(command: str, *, root: Path) -> bool:
    fixed = {
        "just check",
        "just model-check",
        "just model-reference-check",
        "just package-check",
        "just system-evolution-check",
        "just skills-check",
        "just lint",
        "just typecheck",
    }
    if command in fixed:
        return True
    if any(token in command for token in ("\n", "\r", ";", "&&", "||", "\u0060", "$(")):
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if parts[:3] != ["uv", "run", "pytest"]:
        return False
    targets = [part for part in parts[3:] if not part.startswith("-")]
    return bool(targets) and all(_is_test_target(target, root) for target in targets)


def _is_test_target(target: str, root: Path) -> bool:
    path_text = target.split("::", 1)[0]
    if not path_text.startswith("tests/"):
        return False
    candidate = (root / path_text).resolve()
    return candidate.is_file() and candidate.is_relative_to((root / "tests").resolve())


def _evidence_references(record: dict[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    blocker = record["evolution"]["blocker"]
    if blocker is not None:
        result.extend(("evolution blocker", value) for value in blocker["evidence_refs"])
    for collection, label in (
        (record["findings"], "finding"),
        (record["decisions"], "decision"),
        (record["work_items"], "work item"),
    ):
        for entry in collection:
            result.extend((f"{label} {entry['id']}", value) for value in entry["evidence_refs"])
    for item in record["work_items"]:
        if item["blocker"] is not None:
            result.extend(
                (f"work item {item['id']} blocker", value)
                for value in item["blocker"]["evidence_refs"]
            )
    result.extend(("closure", value) for value in record["closure"]["evidence_refs"])
    for review in record["reviews"]:
        result.extend((f"review {review['lens']}", value) for value in review["evidence_refs"])
    return result


def evidence_reference_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    result: list[str] = []
    for label, reference in _evidence_references(record):
        result.extend(_evidence_reference_findings(reference, label=label, root=root))
        if reference.startswith("command:") and not is_vellis_check_command(
            reference.removeprefix("command:"), root=root
        ):
            result.append(f"{label} command evidence is not a Vellis check: {reference}")
    return result


def _authority_references(record: dict[str, Any]) -> list[tuple[str, str]]:
    result = [("scope", value) for value in record["scope"]["authority_scope"]]
    for collection, label in (
        (record["findings"], "finding"),
        (record["decisions"], "decision"),
    ):
        for entry in collection:
            result.extend((f"{label} {entry['id']}", value) for value in entry["authority_refs"])
    for item in record["work_items"]:
        result.extend((f"work item {item['id']}", value) for value in item["authority_refs"])
    return result


def _model_packages(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    pattern = r"^\s*package\s+(?:'([^']+)'|([A-Za-z_]\w*))\s*\{"
    for path in sorted((root / "model").glob("*.sysml")):
        source = path.read_text(encoding="utf-8")
        for package in re.findall(pattern, source, re.M):
            result[package[0] or package[1]] = source
    return result


def authority_reference_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    packages = _model_packages(root)
    result: list[str] = []
    for label, reference in _authority_references(record):
        if "::" not in reference:
            continue
        package, member = reference.split("::", 1)
        source = packages.get(package)
        if source is None or not _member_resolves(member, source):
            result.append(f"{label} authority reference does not resolve: {reference}")
    return result


def _member_resolves(member: str, source: str) -> bool:
    if member.startswith("'") and member.endswith("'"):
        return member in source
    return re.search(rf"(?<![\w]){re.escape(member)}(?![\w])", source) is not None


def _git_references(record: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for name in ("source", "target"):
        baseline = record["baselines"][name]
        if baseline is not None:
            result.update(
                value
                for value in baseline.values()
                if isinstance(value, str) and value.startswith("git:")
            )
    for item in record["work_items"]:
        values = (item["checkpoint"],)
        result.update(
            value for value in values if isinstance(value, str) and value.startswith("git:")
        )
    for review in record["reviews"]:
        value = review["checkpoint"]
        if isinstance(value, str) and value.startswith("git:"):
            result.add(value)
    values = (
        record["evolution"]["approval"]["checkpoint"],
        record["evolution"]["checkpoint"],
        record["closure"]["checkpoint"],
    )
    result.update(value for value in values if isinstance(value, str) and value.startswith("git:"))
    return result


def git_checkpoint_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    return [
        f"Git checkpoint does not resolve to a commit: {reference}"
        for reference in sorted(_git_references(record))
        if not _commit_exists(reference.removeprefix("git:"), root)
    ]


def _commit_exists(revision: str, root: Path) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def git_text(root: Path, *arguments: str) -> str:
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


def repository_baseline(root: Path) -> dict[str, str]:
    head = git_text(root, "rev-parse", "HEAD")
    return {
        "model": f"sha256:{authority_digest(root)}",
        "implementation": f"git:{head}",
        "language": f"sha256:{_sha256(root / 'model' / 'config' / 'language.lock.json')}",
        "execution_environment": f"sha256:{_sha256(root / 'uv.lock')}",
        "checkpoint": f"git:{head}",
    }


def repository_baseline_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    """Compare the record's own baseline with the repository, computing rather than storing.

    The record used to carry an observed baseline that a check then compared with the
    repository, so every ordinary commit made the stored copy stale and demanded a record
    commit to restamp it. The repository is the observation; only the bound baseline is
    recorded.
    """
    actual = repository_baseline(root)
    bound = record["baselines"]["target"] or record["baselines"]["source"]
    result = [
        f"evolution is bound to a stale {dimension} baseline"
        for dimension in ("model", "language", "execution_environment")
        if bound[dimension] is not None and bound[dimension] != actual[dimension]
    ]
    if record["evolution"]["lifecycle"] == "complete":
        result.extend(_complete_baseline_findings(record, actual, root))
    return result


def _complete_baseline_findings(
    record: dict[str, Any], actual: dict[str, str], root: Path
) -> list[str]:
    target = record["baselines"]["target"]
    if target is None:
        return []
    result: list[str] = []
    if not target["implementation"].startswith("git:"):
        return ["complete target implementation is not a Vellis Git checkpoint"]
    if target["checkpoint"] != target["implementation"]:
        result.append("complete target checkpoint must equal its implementation checkpoint")
    target_revision = target["implementation"].removeprefix("git:")
    head_revision = actual["implementation"].removeprefix("git:")
    if target_revision != head_revision and not _only_record_changed(
        target_revision, head_revision, root
    ):
        result.append("complete target implementation is not the reviewed repository checkpoint")
    dirty = git_text(root, "status", "--porcelain", "--untracked-files=no").splitlines()
    if dirty:
        result.append("complete evolution has dirty tracked state outside its record")
    return result


def _only_record_changed(old: str, new: str, root: Path) -> bool:
    try:
        changed = git_text(root, "diff", "--name-only", old, new).splitlines()
    except RuntimeError:
        return False
    return changed == ["system-evolution.yaml"]


def _approvals(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("evolution", record["evolution"]["approval"])]


def approval_checkpoint_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    result: list[str] = []
    for label, approval in _approvals(record):
        if approval["status"] != "accepted":
            continue
        result.extend(_one_approval_findings(label, approval, record, root))
    return result


def _one_approval_findings(
    label: str,
    approval: dict[str, Any],
    record: dict[str, Any],
    root: Path,
) -> list[str]:
    checkpoint = approval["checkpoint"]
    if not isinstance(checkpoint, str) or not checkpoint.startswith("git:"):
        return [f"accepted {label} approval is not bound to a Vellis Git checkpoint"]
    historical = _historical_record(checkpoint.removeprefix("git:"), root)
    if historical is None:
        return [f"accepted {label} approval checkpoint is not reconstructible"]
    subject, old_approval, current_projection, old_projection = _approval_projections(
        label, approval, record, historical
    )
    if old_approval.get("status") not in {"pending", "accepted"}:
        return [
            f"accepted {label} approval names a checkpoint where it was not awaiting a decision"
        ]
    if not subject:
        return [f"accepted {label} approval is absent from its checkpoint"]
    if current_projection != old_projection:
        return [f"accepted {label} consequence differs from its approval checkpoint"]
    return []


def _historical_record(revision: str, root: Path) -> dict[str, Any] | None:
    try:
        source = git_text(root, "show", f"{revision}:system-evolution.yaml")
        value = yaml.load(source, Loader=UniqueKeyLoader)  # noqa: S506
    except RuntimeError, yaml.YAMLError:
        return None
    return value if isinstance(value, dict) else None


def _approval_projections(
    label: str,
    approval: dict[str, Any],
    record: dict[str, Any],
    historical: dict[str, Any],
) -> tuple[object, dict[str, Any], dict[str, Any], dict[str, Any]]:
    subject = historical.get("evolution", {})
    old_approval = subject.get("approval", {})
    current = _evolution_approval_projection(record)
    old = _evolution_approval_projection(historical)
    current["reason"] = approval["reason"]
    old["reason"] = old_approval.get("reason")
    return subject, old_approval, current, old


def _evolution_approval_projection(record: dict[str, Any]) -> dict[str, Any]:
    evolution = record.get("evolution", {})
    return {
        "objective": evolution.get("objective"),
        "observable_distinction": evolution.get("observable_distinction"),
        "scope": record.get("scope"),
    }


def repository_findings(record: dict[str, Any], *, root: Path) -> list[str]:
    result = evidence_reference_findings(record, root=root)
    result.extend(authority_reference_findings(record, root=root))
    result.extend(git_checkpoint_findings(record, root=root))
    result.extend(repository_baseline_findings(record, root=root))
    result.extend(approval_checkpoint_findings(record, root=root))
    return result
