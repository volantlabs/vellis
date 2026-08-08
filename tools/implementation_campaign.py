from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator

try:
    from . import sysml_validator
    from .model_layout import (
        AUTHORED_MODEL_PACKAGES,
        IMPLEMENTATION_CAMPAIGN_PATH,
        IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH,
        ROOT,
    )
except ImportError:  # pragma: no cover - direct script execution
    import sysml_validator  # type: ignore[no-redef]
    from model_layout import (  # type: ignore[no-redef]
        AUTHORED_MODEL_PACKAGES,
        IMPLEMENTATION_CAMPAIGN_PATH,
        IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH,
        ROOT,
    )


APPROVAL_CHECKPOINT = re.compile(r"approval:(?P<plan>[0-9a-f]{40})\Z")
SLICE_CHECKPOINT = re.compile(
    r"slice:(?P<slice>S[0-9]{3}):(?P<plan>[0-9a-f]{12}):(?P<attempt>[1-9][0-9]*)\Z"
)
CLOSURE_CHECKPOINT = re.compile(r"closure:(?P<plan>[0-9a-f]{12}):(?P<attempt>[1-9][0-9]*)\Z")


@dataclass(frozen=True)
class CommitTrailers:
    values: dict[str, list[str]]
    raw_lines: tuple[str, ...]


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


def _sysml_header_tokens(source: str) -> list[str]:
    """Tokenize enough of a SysML file header to establish project provenance.

    Qualified-reference meaning is still resolved by the pinned validator. This small lexer only
    enforces this project's one-root-package-per-authored-file convention without trusting a
    filename map alone.
    """
    tokens: list[str] = []
    index = 0
    while index < len(source) and len(tokens) < 3:
        if source[index].isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline == -1 else newline + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end == -1:
                return []
            index = end + 2
            continue
        if source[index] == "'":
            end = index + 1
            while end < len(source):
                if source[end] == "'" and source[end - 1] != "\\":
                    break
                end += 1
            if end >= len(source):
                return []
            tokens.append(source[index + 1 : end])
            index = end + 1
            continue
        match = re.match(r"[A-Za-z_]\w*", source[index:])
        if match is not None:
            tokens.append(match.group(0))
            index += len(match.group(0))
            continue
        tokens.append(source[index])
        index += 1
    return tokens


def _authored_model_package_findings(root: Path) -> list[str]:
    findings: list[str] = []
    expected_by_file = {path: package for package, path in AUTHORED_MODEL_PACKAGES.items()}
    for path in authored_model_files(root):
        relative = path.relative_to(root).as_posix()
        tokens = _sysml_header_tokens(path.read_text(encoding="utf-8"))
        declared = (
            tokens[1] if len(tokens) >= 3 and tokens[0] == "package" and tokens[2] == "{" else None
        )
        expected = expected_by_file.get(relative)
        if declared != expected:
            findings.append(
                f"authored model package provenance mismatch for {relative}: "
                f"expected {expected or 'no package'}, found {declared or 'no root package'}"
            )
    return findings


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


def _markdown_anchors(source: str) -> set[str]:
    anchors: set[str] = set()
    counts: Counter[str] = Counter()
    for line in source.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match is None:
            continue
        heading = match.group(1).strip().lower()
        base = "".join(
            character for character in heading if character.isalnum() or character in " -_"
        )
        base = re.sub(r"\s+", "-", base)
        suffix = counts[base]
        counts[base] += 1
        anchors.add(base if suffix == 0 else f"{base}-{suffix}")
    return anchors


def _python_test_nodes(source: str) -> set[str]:
    try:
        module = ast.parse(source)
    except SyntaxError:
        return set()
    nodes: set[str] = set()
    for item in module.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith(
            "test_"
        ):
            nodes.add(item.name)
        elif isinstance(item, ast.ClassDef):
            for child in item.body:
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and child.name.startswith("test_"):
                    nodes.add(f"{item.name}::{child.name}")
    return nodes


def _evidence_fragment_exists(path: str, source: str, fragment: str) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".md":
        return fragment in _markdown_anchors(source)
    if suffix == ".py":
        return fragment in _python_test_nodes(source)
    return False


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
        candidate = root / Path(*path.parts)
        try:
            resolved_root = root.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
        except OSError:
            return [f"{label} path evidence does not exist: {path_text}"]
        if not resolved.is_relative_to(resolved_root):
            return [f"{label} path evidence escapes the repository through a symlink: {path_text}"]
        if not resolved.is_file() or candidate.is_symlink():
            return [f"{label} path evidence does not exist: {path_text}"]
        try:
            source = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return [f"{label} path evidence must be UTF-8 Markdown or Python: {path_text}"]
        if not _evidence_fragment_exists(path_text, source, fragment):
            return [f"{label} evidence fragment does not resolve: {path_text}#{fragment}"]
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
    if set(AUTHORED_MODEL_PACKAGES.values()) != set(expected_files):
        findings.append("project model-package provenance must cover every authored model file")
    findings.extend(_authored_model_package_findings(root))

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
                continue
            root_package = reference["model_ref"].partition("::")[0]
            expected_source = AUTHORED_MODEL_PACKAGES.get(root_package)
            if expected_source is None:
                findings.append(
                    f"authority {entry['id']} model reference has an unknown root package "
                    f"{root_package}"
                )
            elif reference["source"] != expected_source:
                findings.append(
                    f"authority {entry['id']} reference {reference['model_ref']} is owned by "
                    f"{expected_source}, not {reference['source']}"
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
    execution_states = {"ready", "active"}
    if approval["status"] != "accepted":
        if any(entry["lifecycle"] in execution_states for entry in slice_entries):
            findings.append("unapproved plans may not have ready or active slices")
        if campaign_lifecycle in {"ready", "active", "complete"}:
            findings.append("an unapproved campaign may not be ready, active, or complete")
    if approval["status"] == "accepted" and approval["checkpoint"] is None:
        findings.append("accepted plan approval requires a checkpoint")
    if approval["status"] == "accepted" and campaign_lifecycle not in {
        "ready",
        "active",
        "complete",
    }:
        findings.append("accepted approval requires a ready, active, or complete campaign")
    if campaign_lifecycle == "awaiting-plan-approval" and approval["status"] != "pending":
        findings.append("an awaiting-plan-approval campaign requires pending approval")

    if campaign_lifecycle == "active" and len(active) != 1:
        findings.append("an active campaign must have exactly one active slice")
    if active and campaign_lifecycle != "active":
        findings.append("an active slice requires an active campaign")
    ready = [entry for entry in slice_entries if entry["lifecycle"] == "ready"]
    incomplete = [entry for entry in slice_entries if entry["lifecycle"] != "complete"]
    eligible = [
        entry
        for entry in incomplete
        if entry["lifecycle"] in {"pending", "ready", "active"}
        and all(
            slices[dependency]["lifecycle"] == "complete" for dependency in entry["dependencies"]
        )
    ]
    if campaign_lifecycle == "ready":
        if incomplete and len(ready) != 1:
            findings.append("a ready campaign must have exactly one ready slice")
        if ready and eligible:
            expected = min(eligible, key=lambda entry: entry["order"])
            if ready[0]["id"] != expected["id"]:
                findings.append(
                    f"ready slice {ready[0]['id']} is not the lowest-ordered dependency-ready "
                    f"slice {expected['id']}"
                )
    if campaign_lifecycle == "active" and active:
        if ready:
            findings.append("an active campaign may not retain a separate ready slice")
        if eligible:
            expected = min(eligible, key=lambda entry: entry["order"])
            if active[0]["id"] != expected["id"]:
                findings.append(
                    f"active slice {active[0]['id']} is not the lowest-ordered dependency-ready "
                    f"slice {expected['id']}"
                )

    campaign_blocker = campaign["campaign"]["blocker"]
    slice_blockers = [entry for entry in slice_entries if entry["blocker"] is not None]
    blocker_present = campaign_blocker is not None or bool(slice_blockers)
    if blocker_present:
        if campaign_lifecycle not in {"blocked", "stale"}:
            findings.append("any campaign or slice blocker must stop campaign execution")
        if approval["status"] != "changes-required" or approval["checkpoint"] is not None:
            findings.append("a blocker invalidates approval and its checkpoint")
    if campaign_lifecycle in {"blocked", "stale"} and approval["status"] != "changes-required":
        findings.append("a blocked or stale campaign requires changes-required approval")
    if campaign_lifecycle in {"ready", "active", "complete"} and blocker_present:
        findings.append("an executable or complete campaign may not retain a blocker")
    if campaign_lifecycle == "blocked" and campaign_blocker is None and not slice_blockers:
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
            skipped = [
                candidate["id"]
                for candidate in slice_entries
                if candidate["order"] < entry["order"] and candidate["lifecycle"] != "complete"
            ]
            if skipped:
                findings.append(
                    f"complete slice {slice_id} skipped lower-ordered slices: " + ", ".join(skipped)
                )

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


def qualified_model_reference_findings(
    campaign: dict[str, Any],
    *,
    model_files: list[Path] | None = None,
    validator_lock_path: Path = sysml_validator.VALIDATOR_LOCK_PATH,
) -> list[str]:
    authority_references = [
        reference["model_ref"]
        for authority in campaign["authority"]
        for reference in authority["refs"]
    ]
    verification_references = [
        reference for entry in campaign["slices"] for reference in entry["verification_refs"]
    ]
    references = [*authority_references, *verification_references]
    unresolved = sysml_validator.unresolved_model_references(
        references,
        model_files=model_files,
        validator_lock_path=validator_lock_path,
    )
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


def _git_bytes(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(  # noqa: S603
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout


def _commit_trailers(root: Path, commit: str) -> CommitTrailers:
    body = _git(root, "show", "-s", "--format=%B", commit)
    completed = subprocess.run(  # noqa: S603
        ["git", "interpret-trailers", "--parse"],
        cwd=root,
        input=body,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git interpret-trailers failed: {completed.stderr.strip()}")
    trailers: dict[str, list[str]] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            trailers.setdefault(key.strip(), []).append(value.strip())
    body_lines = body.splitlines()
    final_blank = max(
        (index for index, line in enumerate(body_lines) if not line.strip()),
        default=-1,
    )
    return CommitTrailers(trailers, tuple(body_lines[final_blank + 1 :]))


def _checkpoint_trailer_findings(
    checkpoint: str,
    trailers: CommitTrailers,
    expected: dict[str, str],
) -> list[str]:
    findings: list[str] = []
    campaign_trailers: dict[str, list[tuple[str, str]]] = {}
    for key, values in trailers.values.items():
        if key.lower().startswith("campaign-"):
            campaign_trailers.setdefault(key.lower(), []).extend((key, value) for value in values)
    for key, value in expected.items():
        entries = campaign_trailers.get(key.lower(), [])
        exact_line = f"{key}: {value}"
        if entries != [(key, value)] or trailers.raw_lines.count(exact_line) != 1:
            findings.append(
                f"checkpoint {checkpoint} requires exactly one canonical {key}: {value}; "
                f"found {entries}"
            )
    unexpected = sorted(set(campaign_trailers) - {key.lower() for key in expected})
    expected_lines = {f"{key}: {value}" for key, value in expected.items()}
    unexpected_raw = sorted(
        line
        for line in trailers.raw_lines
        if line.partition(":")[0].strip().lower().startswith("campaign-")
        and line not in expected_lines
    )
    if unexpected:
        findings.append(
            f"checkpoint {checkpoint} has unexpected campaign trailers: " + ", ".join(unexpected)
        )
    if unexpected_raw:
        findings.append(
            f"checkpoint {checkpoint} has noncanonical campaign trailer lines: "
            + ", ".join(unexpected_raw)
        )
    return findings


def _trailer_values(trailers: CommitTrailers, key: str) -> list[str]:
    return [
        value
        for actual_key, values in trailers.values.items()
        if actual_key.lower() == key.lower()
        for value in values
    ]


def _checkpoint_commits(
    checkpoint: str,
    commit_trailers: dict[str, CommitTrailers],
) -> list[str]:
    return [
        commit
        for commit, trailers in commit_trailers.items()
        if checkpoint in _trailer_values(trailers, "Campaign-Checkpoint")
    ]


def _direct_checkpoint_parent_findings(
    *,
    root: Path,
    commit: str,
    checkpoint: str,
    previous_checkpoint: str | None,
    commit_trailers: dict[str, CommitTrailers],
) -> list[str]:
    if previous_checkpoint is None:
        return [f"checkpoint {checkpoint} does not identify its preceding recovery checkpoint"]
    previous_commits = _checkpoint_commits(previous_checkpoint, commit_trailers)
    if len(previous_commits) != 1:
        return [
            f"checkpoint {checkpoint} preceding checkpoint {previous_checkpoint} must resolve "
            f"exactly once; found {len(previous_commits)}"
        ]
    parents = _git(root, "rev-list", "--parents", "-n", "1", commit).split()
    if len(parents) != 2 or parents[1] != previous_commits[0]:
        return [
            f"checkpoint {checkpoint} must be a direct single-parent child of preceding "
            f"checkpoint {previous_checkpoint}"
        ]
    return []


def _plan_projection(campaign: dict[str, Any]) -> dict[str, Any]:
    """Return immutable plan-bearing content, excluding only execution observations."""
    return {
        "schema_version": campaign["schema_version"],
        "campaign": {
            "id": campaign["campaign"]["id"],
            "objective": campaign["campaign"]["objective"],
        },
        "model_baseline": campaign["model_baseline"],
        "authority": [
            {key: entry[key] for key in ("id", "label", "refs", "planned_coverage", "slice_ids")}
            for entry in campaign["authority"]
        ],
        "slices": [
            {
                key: entry[key]
                for key in (
                    "id",
                    "order",
                    "label",
                    "kind",
                    "dependencies",
                    "authority",
                    "verification_refs",
                    "realization_decisions",
                )
            }
            for entry in campaign["slices"]
        ],
        "closure": {"authority_coverage": campaign["closure"]["authority_coverage"]},
    }


def _plan_projection_key(campaign: dict[str, Any]) -> str:
    source = json.dumps(_plan_projection(campaign), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _checkpoint_ids(campaign: dict[str, Any]) -> set[str]:
    checkpoints = {
        campaign["campaign"]["plan_approval"]["checkpoint"],
        campaign["campaign"]["checkpoint"],
        campaign["closure"]["checkpoint"],
        *(entry["checkpoint"] for entry in campaign["slices"]),
    }
    return {checkpoint for checkpoint in checkpoints if checkpoint is not None}


def _committed_evidence_findings(*, root: Path, commit: str, references: list[str]) -> list[str]:
    findings: list[str] = []
    for reference in references:
        if not reference.startswith("path:"):
            continue
        value = reference.removeprefix("path:")
        path, _, fragment = value.partition("#")
        mode_findings = _committed_regular_path_findings(root=root, commit=commit, path=path)
        if mode_findings:
            findings.extend(mode_findings)
            continue
        try:
            source = _git_bytes(root, "show", f"{commit}:{path}").decode("utf-8")
        except RuntimeError, UnicodeDecodeError:
            findings.append(f"checkpoint {commit} does not contain UTF-8 evidence path {path}")
            continue
        if not _evidence_fragment_exists(path, source, fragment):
            findings.append(
                f"checkpoint {commit} evidence fragment does not resolve: {path}#{fragment}"
            )
    return findings


def _committed_path_mode(*, root: Path, commit: str, path: str) -> str | None:
    records = _git_bytes(root, "ls-tree", "-z", commit, "--", path).split(b"\0")
    for record in records:
        metadata, separator, recorded_path = record.partition(b"\t")
        if not separator or recorded_path.decode("utf-8", errors="surrogateescape") != path:
            continue
        mode, _, _ = metadata.partition(b" ")
        return mode.decode("ascii")
    return None


def _committed_regular_path_findings(*, root: Path, commit: str, path: str) -> list[str]:
    pure_path = PurePosixPath(path)
    for depth in range(1, len(pure_path.parts)):
        ancestor = PurePosixPath(*pure_path.parts[:depth]).as_posix()
        mode = _committed_path_mode(root=root, commit=commit, path=ancestor)
        if mode != "040000":
            return [
                f"checkpoint {commit} path {path} has non-directory ancestor "
                f"{ancestor} with mode {mode or 'missing'}"
            ]
    mode = _committed_path_mode(root=root, commit=commit, path=path)
    if mode not in {"100644", "100755"}:
        return [
            f"checkpoint {commit} path {path} must be a regular committed file; "
            f"found mode {mode or 'missing'}"
        ]
    return []


def _committed_campaign_findings(
    campaign: dict[str, Any],
    *,
    root: Path,
    commit: str,
    resolve_qualified_references: bool = False,
) -> list[str]:
    schema_relative = IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH.relative_to(ROOT)
    authority_files = campaign.get("model_baseline", {}).get("authority_files", [])
    expected_authority_files = sorted(AUTHORED_MODEL_PACKAGES.values())
    if authority_files != expected_authority_files:
        return [f"checkpoint {commit} has an unsafe or incomplete authored model file list"]
    required_paths = [
        *authority_files,
        "model/config/language.lock.json",
        "model/config/validator.lock.json",
        schema_relative.as_posix(),
    ]
    for _, reference in _all_evidence_references(campaign):
        if not reference.startswith("path:"):
            continue
        path_text = reference.removeprefix("path:").partition("#")[0]
        path = PurePosixPath(path_text)
        if not path_text or "\\" in path_text or path.is_absolute() or ".." in path.parts:
            return [f"checkpoint {commit} contains an unsafe evidence path {path_text}"]
        required_paths.append(path_text)
    with tempfile.TemporaryDirectory(prefix="vellis-campaign-checkpoint-") as temporary:
        snapshot = Path(temporary)
        for relative in dict.fromkeys(required_paths):
            mode_findings = _committed_regular_path_findings(
                root=root,
                commit=commit,
                path=relative,
            )
            if mode_findings:
                return mode_findings
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                destination.write_bytes(_git_bytes(root, "show", f"{commit}:{relative}"))
            except RuntimeError as error:
                return [
                    f"checkpoint {commit} is missing required committed path {relative}: {error}"
                ]
        findings = validate_campaign(
            campaign,
            root=snapshot,
            schema_path=snapshot / schema_relative,
        )
        if not findings and resolve_qualified_references:
            findings.extend(
                qualified_model_reference_findings(
                    campaign,
                    model_files=authored_model_files(snapshot),
                    validator_lock_path=(snapshot / "model" / "config" / "validator.lock.json"),
                )
            )
        return findings


def _expected_approval_campaign(parent: dict[str, Any], *, checkpoint: str) -> dict[str, Any]:
    expected = copy.deepcopy(parent)
    expected["campaign"]["lifecycle"] = "ready"
    expected["campaign"]["plan_approval"] = {
        "status": "accepted",
        "checkpoint": checkpoint,
    }
    expected["campaign"]["checkpoint"] = checkpoint
    slices = expected["slices"]
    eligible = [
        entry
        for entry in slices
        if entry["lifecycle"] == "pending"
        and all(
            next(item for item in slices if item["id"] == dependency)["lifecycle"] == "complete"
            for dependency in entry["dependencies"]
        )
    ]
    if eligible:
        min(eligible, key=lambda entry: entry["order"])["lifecycle"] = "ready"
    return expected


def checkpoint_binding_findings(campaign: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    checkpoints = _checkpoint_ids(campaign)
    if not checkpoints:
        return findings
    head = _git(root, "rev-parse", "HEAD")
    commit_trailers = {
        commit: _commit_trailers(root, commit)
        for commit in _git(root, "log", "HEAD", "--format=%H").splitlines()
    }
    resolved_plan_keys: set[str] = set()
    approved_plans: dict[str, dict[str, Any] | None] = {}
    for checkpoint in sorted(checkpoints):
        commits = _checkpoint_commits(checkpoint, commit_trailers)
        if len(commits) != 1:
            findings.append(
                f"checkpoint {checkpoint} must resolve to exactly one reachable commit; "
                f"found {len(commits)}"
            )
            continue

        commit = commits[0]
        trailers = commit_trailers[commit]
        try:
            committed = load_campaign_text(
                _git(root, "show", f"{commit}:implementation-campaign.yaml"),
                label=f"{commit}:implementation-campaign.yaml",
            )
        except (RuntimeError, ValueError, yaml.YAMLError) as error:
            findings.append(f"checkpoint {checkpoint} has no readable committed campaign: {error}")
            continue
        plan_key = _plan_projection_key(committed)
        resolve_references = plan_key not in resolved_plan_keys
        snapshot_findings = _committed_campaign_findings(
            committed,
            root=root,
            commit=commit,
            resolve_qualified_references=resolve_references,
        )
        if resolve_references:
            resolved_plan_keys.add(plan_key)
        findings.extend(
            f"checkpoint {checkpoint} committed campaign is invalid: {finding}"
            for finding in snapshot_findings
        )
        if campaign["campaign"]["checkpoint"] == checkpoint and commit != head:
            findings.append(
                f"current campaign checkpoint {checkpoint} resolves to {commit}, not HEAD {head}"
            )

        committed_approval = committed["campaign"]["plan_approval"]
        if committed_approval["status"] == "accepted":
            committed_approval_match = APPROVAL_CHECKPOINT.fullmatch(
                committed_approval["checkpoint"] or ""
            )
            if committed_approval_match is None:
                findings.append(
                    f"checkpoint {checkpoint} has accepted approval without a valid plan commit"
                )
            else:
                approved_plan_sha = committed_approval_match.group("plan")
                if approved_plan_sha not in approved_plans:
                    try:
                        approved_plans[approved_plan_sha] = load_campaign_text(
                            _git(
                                root,
                                "show",
                                f"{approved_plan_sha}:implementation-campaign.yaml",
                            ),
                            label=f"{approved_plan_sha}:implementation-campaign.yaml",
                        )
                    except (RuntimeError, ValueError, yaml.YAMLError) as error:
                        findings.append(
                            f"checkpoint {checkpoint} cannot read approved plan "
                            f"{approved_plan_sha}: {error}"
                        )
                        approved_plans[approved_plan_sha] = None
                approved_plan = approved_plans[approved_plan_sha]
                if approved_plan is not None and _plan_projection(committed) != _plan_projection(
                    approved_plan
                ):
                    findings.append(
                        f"checkpoint {checkpoint} changed plan-bearing content after approval"
                    )

        approval_match = APPROVAL_CHECKPOINT.fullmatch(checkpoint)
        slice_match = SLICE_CHECKPOINT.fullmatch(checkpoint)
        closure_match = CLOSURE_CHECKPOINT.fullmatch(checkpoint)
        if approval_match is not None:
            findings.extend(
                _checkpoint_trailer_findings(
                    checkpoint,
                    trailers,
                    {
                        "Campaign-Checkpoint": checkpoint,
                        "Campaign-Approval": "accepted",
                    },
                )
            )
            parents = _git(root, "rev-list", "--parents", "-n", "1", commit).split()
            if len(parents) != 2 or parents[1] != approval_match.group("plan"):
                findings.append(
                    f"approval checkpoint {checkpoint} must be directly based on its plan commit"
                )
            try:
                parent = load_campaign_text(
                    _git(
                        root,
                        "show",
                        f"{approval_match.group('plan')}:implementation-campaign.yaml",
                    ),
                    label=(f"{approval_match.group('plan')}:implementation-campaign.yaml"),
                )
            except (RuntimeError, ValueError, yaml.YAMLError) as error:
                findings.append(
                    f"approval checkpoint {checkpoint} cannot read its approved plan: {error}"
                )
                parent = None
            if parent is not None:
                parent_findings = _committed_campaign_findings(
                    parent,
                    root=root,
                    commit=approval_match.group("plan"),
                    resolve_qualified_references=(
                        _plan_projection_key(parent) not in resolved_plan_keys
                    ),
                )
                resolved_plan_keys.add(_plan_projection_key(parent))
                findings.extend(
                    f"approved plan {approval_match.group('plan')} is invalid: {finding}"
                    for finding in parent_findings
                )
                if (
                    parent["campaign"]["lifecycle"] != "awaiting-plan-approval"
                    or parent["campaign"]["plan_approval"]
                    != {"status": "pending", "checkpoint": None}
                    or parent["campaign"]["blocker"] is not None
                ):
                    findings.append(
                        f"approval checkpoint {checkpoint} parent is not awaiting clean approval"
                    )
                if committed != _expected_approval_campaign(parent, checkpoint=checkpoint):
                    findings.append(
                        f"approval checkpoint {checkpoint} changed plan-bearing campaign content"
                    )
            changed_paths = set(
                _git(
                    root,
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    commit,
                ).splitlines()
            )
            if changed_paths != {"implementation-campaign.yaml"}:
                findings.append(
                    f"approval checkpoint {checkpoint} must change only "
                    "implementation-campaign.yaml"
                )
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
            findings.extend(
                _checkpoint_trailer_findings(
                    checkpoint,
                    trailers,
                    {
                        "Campaign-Checkpoint": checkpoint,
                        "Campaign-Authority-Review": "clean",
                        "Campaign-Engineering-Review": "clean",
                    },
                )
            )
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
                        root=root,
                        commit=commit,
                        references=entry["evidence_refs"],
                    )
                )
            if committed["campaign"]["checkpoint"] != checkpoint:
                findings.append(f"slice checkpoint {checkpoint} is not the campaign checkpoint")
            prior_completed = [
                item
                for item in committed["slices"]
                if item["lifecycle"] == "complete"
                and entry is not None
                and item["order"] < entry["order"]
            ]
            previous_checkpoint = (
                max(prior_completed, key=lambda item: item["order"])["checkpoint"]
                if prior_completed
                else committed["campaign"]["plan_approval"]["checkpoint"]
            )
            findings.extend(
                _direct_checkpoint_parent_findings(
                    root=root,
                    commit=commit,
                    checkpoint=checkpoint,
                    previous_checkpoint=previous_checkpoint,
                    commit_trailers=commit_trailers,
                )
            )
        elif closure_match is not None:
            findings.extend(
                _checkpoint_trailer_findings(
                    checkpoint,
                    trailers,
                    {
                        "Campaign-Checkpoint": checkpoint,
                        "Campaign-Closure-Review": "clean",
                    },
                )
            )
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
                        root=root,
                        commit=commit,
                        references=closure["evidence_refs"],
                    )
                )
            completed_slices = [
                item for item in committed["slices"] if item["lifecycle"] == "complete"
            ]
            previous_checkpoint = (
                max(completed_slices, key=lambda item: item["order"])["checkpoint"]
                if completed_slices
                else committed["campaign"]["plan_approval"]["checkpoint"]
            )
            findings.extend(
                _direct_checkpoint_parent_findings(
                    root=root,
                    commit=commit,
                    checkpoint=checkpoint,
                    previous_checkpoint=previous_checkpoint,
                    commit_trailers=commit_trailers,
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
    blocker_label = "none"
    if blocker is not None:
        blocker_label = blocker["classification"] + ": " + blocker["summary"]
    else:
        blocked_slice = min(
            (entry for entry in slice_entries if entry["blocker"] is not None),
            key=lambda entry: entry["order"],
            default=None,
        )
        if blocked_slice is not None:
            slice_blocker = blocked_slice["blocker"]
            blocker_label = (
                f"{blocked_slice['id']} {slice_blocker['classification']}: "
                f"{slice_blocker['summary']}"
            )
    lines = [
        f"Campaign: {campaign['campaign']['id']}",
        f"Lifecycle: {campaign['campaign']['lifecycle']}",
        f"Baseline: {campaign['model_baseline']['status']}",
        f"Plan approval: {campaign['campaign']['plan_approval']['status']}",
        "Slices: " + ", ".join(f"{name}={counts[name]}" for name in sorted(counts)),
        f"Active: {active['id'] + ' ' + active['label'] if active else 'none'}",
        f"Next: {ready[0]['id'] + ' ' + ready[0]['label'] if ready else 'none'}",
        f"Blocker: {blocker_label}",
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
