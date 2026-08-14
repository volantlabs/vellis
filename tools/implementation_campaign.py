from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
from collections import Counter
from functools import cache
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
WORKER_RESULT_SCHEMA_PATH = (
    ROOT
    / ".agents"
    / "skills"
    / "sysml-implementation-campaign"
    / "assets"
    / "campaign-worker-result.schema.json"
)
REVIEW_LENSES = ("authority", "engineering")
CLOSURE_WORK_ITEM = "closure"


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


@cache
def _committed_evidence_source(
    root_text: str, revision: str, path_text: str
) -> tuple[str, str] | None:
    root = Path(root_text)
    try:
        listing = _git(root, "ls-tree", revision, "--", path_text)
        source = _git(root, "show", f"{revision}:{path_text}")
    except RuntimeError:
        return None
    mode = listing.split(maxsplit=1)[0] if listing else ""
    return mode, source


def _evidence_reference_findings(
    reference: str, *, label: str, root: Path, revision: str | None = None
) -> list[str]:
    if reference.startswith("command:"):
        command = reference.removeprefix("command:")
        if (
            not command.strip()
            or command != command.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in command)
        ):
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
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            return [f"{label} path evidence must be path:<repo-relative-path>#<test-or-section>"]
        if revision is not None:
            committed = _committed_evidence_source(str(root.resolve()), revision, path_text)
            if committed is None:
                return [f"{label} path evidence does not exist at checkpoint: {path_text}"]
            mode, source = committed
            if mode not in {"100644", "100755"}:
                return [f"{label} path evidence is not a regular file at checkpoint: {path_text}"]
            if not _evidence_fragment_exists(path_text, source, fragment):
                return [
                    f"{label} evidence fragment does not resolve at checkpoint: "
                    f"{path_text}#{fragment}"
                ]
            return []
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


def _completed_campaign_evidence_revision(campaign: dict[str, Any], *, root: Path) -> str | None:
    """Locate the commit that closed this campaign for durable evidence lookup.

    A completed campaign is historical authority. Later model evolution may retire or
    consolidate its evidence files without erasing the exact committed evidence that
    justified closure.

    The observed baseline is excluded from the match. It is the one part of the record
    that is supposed to move as the repository evolves, and it must be updated in the
    working tree before it can be committed. Matching on it would mean that editing it —
    the only correct response to an evolved model — drops evidence lookup back to the
    closure commit, where evidence renamed since then no longer resolves. The record
    would then be checkable only after committing the very change being checked.
    """
    checkpoint = campaign["closure"]["checkpoint"]
    if checkpoint is None:
        return None
    try:
        commits = _git(
            root, "log", "--format=%H", "--", IMPLEMENTATION_CAMPAIGN_PATH.name
        ).splitlines()
    except RuntimeError:
        return None
    matched: list[str] = []
    fallback: str | None = None
    for commit in commits:
        try:
            recorded = load_campaign_text(
                _git(root, "show", f"{commit}:{IMPLEMENTATION_CAMPAIGN_PATH.name}"),
                label=f"{commit}:{IMPLEMENTATION_CAMPAIGN_PATH.name}",
            )
        except RuntimeError, ValueError, yaml.YAMLError:
            continue
        if _without_observed_baseline(recorded) == _without_observed_baseline(campaign):
            matched.append(commit)
        elif fallback is None and (
            recorded.get("campaign", {}).get("lifecycle") == "complete"
            and recorded.get("closure", {}).get("checkpoint") == checkpoint
        ):
            fallback = commit
    # The earliest commit carrying this record is the one that recorded it. A later commit
    # carries the same content only because nothing has edited it since, and resolving
    # there would look for evidence in a tree that may have retired it in between.
    if matched:
        return matched[-1]
    return fallback


def _without_observed_baseline(campaign: dict[str, Any]) -> dict[str, Any]:
    """Return one campaign record without the baseline that tracks the repository."""
    value = copy.deepcopy(campaign)
    baseline = value.get("model_baseline")
    if isinstance(baseline, dict):
        baseline.pop("observed", None)
    return value


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
        for decision in entry["realization_decisions"]:
            references.extend(
                (
                    f"slice.{entry['id']}.decision.{decision['id']}.evidence_refs[{index}]",
                    reference,
                )
                for index, reference in enumerate(decision["evidence_refs"])
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
    for decision in campaign["closure"]["realization_decisions"]:
        references.extend(
            (f"closure.decision.{decision['id']}.evidence_refs[{index}]", reference)
            for index, reference in enumerate(decision["evidence_refs"])
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
        elif entry["lifecycle"] != "complete" and checkpoint is not None:
            findings.append(f"only a complete slice may carry a checkpoint: {entry['id']}")
        if entry["lifecycle"] == "complete" and checkpoint is not None:
            completed_entries.append(entry)

    closure_checkpoint = campaign["closure"]["checkpoint"]
    if closure_checkpoint is not None and CLOSURE_CHECKPOINT.fullmatch(closure_checkpoint) is None:
        findings.append("closure checkpoint must be closure:<approved-plan-short-sha>:<attempt>")

    approved_plan = approval_match.group("plan") if approval_match is not None else None
    campaign_checkpoint = campaign["campaign"]["checkpoint"]
    if approved_plan is not None:
        # A replan after execution renews approval without invalidating finished work: a slice
        # completed under a superseded plan keeps the label it earned. Only the frontier moves.
        # Every slice completed at or after the first one carrying the current plan must carry it
        # too, so approval cannot silently reopen behind a slice that already advanced. The record
        # alone cannot say which slices predate the renewal, so this bounds the superseded region
        # rather than locating it; checkpoint_binding_findings closes it against the approved plan.
        ordered = sorted(
            (
                (entry, SLICE_CHECKPOINT.fullmatch(entry["checkpoint"]))
                for entry in campaign["slices"]
                if entry["lifecycle"] == "complete" and entry["checkpoint"] is not None
            ),
            key=lambda pair: pair[0]["order"],
        )
        renewed_positions = [
            position
            for position, (_, slice_match) in enumerate(ordered)
            if slice_match is not None and slice_match.group("plan") == approved_plan[:12]
        ]
        frontier = min(renewed_positions, default=len(ordered))
        for entry, slice_match in ordered[frontier:]:
            if slice_match is not None and slice_match.group("plan") != approved_plan[:12]:
                findings.append(
                    f"slice {entry['id']} checkpoint does not use the approved plan commit"
                )
        # The campaign checkpoint names a slice only once one has completed under this approval,
        # so that slice may never be labelled with a superseded plan.
        campaign_plan_match = (
            SLICE_CHECKPOINT.fullmatch(campaign_checkpoint)
            if campaign_checkpoint is not None
            else None
        )
        if (
            campaign_plan_match is not None
            and campaign_plan_match.group("plan") != approved_plan[:12]
        ):
            findings.append("the campaign checkpoint must use the approved plan commit")
        match = (
            CLOSURE_CHECKPOINT.fullmatch(closure_checkpoint)
            if closure_checkpoint is not None
            else None
        )
        if match is not None and match.group("plan") != approved_plan[:12]:
            findings.append("closure checkpoint does not use the approved plan commit")

    if campaign_checkpoint is not None and not any(
        pattern.fullmatch(campaign_checkpoint)
        for pattern in (APPROVAL_CHECKPOINT, SLICE_CHECKPOINT, CLOSURE_CHECKPOINT)
    ):
        findings.append("campaign checkpoint has an unsupported project checkpoint format")
    campaign_lifecycle = campaign["campaign"]["lifecycle"]
    latest_completed = max(completed_entries, key=lambda entry: entry["order"], default=None)
    latest_completed_checkpoint = (
        latest_completed["checkpoint"] if latest_completed is not None else None
    )
    # Until a slice completes under a renewed approval, the approval itself is the latest
    # recoverable state: the newest completed slice was checkpointed under the superseded plan.
    if approved_plan is not None and latest_completed_checkpoint is not None:
        latest_match = SLICE_CHECKPOINT.fullmatch(latest_completed_checkpoint)
        if latest_match is not None and latest_match.group("plan") != approved_plan[:12]:
            latest_completed_checkpoint = None
    campaign_slice_match = (
        SLICE_CHECKPOINT.fullmatch(campaign_checkpoint) if campaign_checkpoint is not None else None
    )
    if campaign_slice_match is not None:
        checkpoint_slice = next(
            (
                entry
                for entry in campaign["slices"]
                if entry["id"] == campaign_slice_match.group("slice")
            ),
            None,
        )
        if (
            checkpoint_slice is None
            or checkpoint_slice["lifecycle"] != "complete"
            or checkpoint_slice["checkpoint"] != campaign_checkpoint
        ):
            findings.append(
                "a campaign slice checkpoint must match that completed slice's checkpoint"
            )
    if campaign_lifecycle in {"planning", "awaiting-plan-approval"}:
        if campaign_checkpoint is not None:
            findings.append("a planning or awaiting-approval campaign may not have a checkpoint")
    elif campaign_lifecycle in {"ready", "active"}:
        if campaign_checkpoint is None:
            findings.append("an executable campaign requires a recoverable campaign checkpoint")
        expected_checkpoint = (
            latest_completed_checkpoint
            if latest_completed_checkpoint is not None
            else approval_checkpoint
        )
        if campaign_checkpoint != expected_checkpoint:
            findings.append(
                "a ready or active campaign checkpoint must be the latest recoverable checkpoint"
            )
    elif campaign_lifecycle in {"blocked", "stale"}:
        # Blocking clears the approval, so the plan identifier is no longer available to say which
        # completed slices predate it. Retaining a prior approval stays legal for the same reason
        # it does while ready: a campaign blocked after a renewal has advanced past its last slice.
        # Only an approval granted after the newest completed slice qualifies. An approval naming
        # the plan that slice already bears predates it, so resting there would fall backward.
        retained_match = (
            APPROVAL_CHECKPOINT.fullmatch(campaign_checkpoint)
            if campaign_checkpoint is not None
            else None
        )
        latest_plan_match = (
            SLICE_CHECKPOINT.fullmatch(latest_completed_checkpoint)
            if latest_completed_checkpoint is not None
            else None
        )
        retained_approval = retained_match is not None and (
            latest_plan_match is None
            or retained_match.group("plan")[:12] != latest_plan_match.group("plan")
        )
        if latest_completed_checkpoint is not None:
            if campaign_checkpoint != latest_completed_checkpoint and not retained_approval:
                findings.append(
                    "a blocked or stale campaign checkpoint must retain the latest completed slice"
                )
        elif campaign_checkpoint is not None and not retained_approval:
            findings.append(
                "a blocked or stale campaign without completed slices may retain only its prior "
                "approval checkpoint"
            )
    if campaign_lifecycle == "complete":
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

    evidence_revision = _completed_campaign_evidence_revision(campaign, root=root)
    for label, reference in _all_evidence_references(campaign):
        findings.extend(
            _evidence_reference_findings(
                reference,
                label=label,
                root=root,
                revision=evidence_revision,
            )
        )
    findings.extend(_checkpoint_format_findings(campaign))

    baseline = campaign["model_baseline"]
    expected_files = [path.relative_to(root).as_posix() for path in authored_model_files(root)]
    if baseline["authority_files"] != expected_files:
        findings.append("model_baseline.authority_files must equal the sorted authored model files")
    if set(AUTHORED_MODEL_PACKAGES.values()) != set(expected_files):
        findings.append("project model-package provenance must cover every authored model file")

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
    closure = campaign["closure"]
    decisions = [
        decision for entry in slice_entries for decision in entry["realization_decisions"]
    ] + closure["realization_decisions"]
    decision_ids = [decision["id"] for decision in decisions]
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
                elif authority_id not in contribution_ids:
                    findings.append(
                        f"slice {slice_id} decision {decision['id']} names authority "
                        f"{authority_id} outside the slice contribution"
                    )
            if not set(decision["evidence_refs"]).issubset(entry["evidence_refs"]):
                findings.append(
                    f"slice {slice_id} decision {decision['id']} evidence must also be "
                    "slice evidence"
                )
            if decision["implementation_status"] == "conforming" and not decision["evidence_refs"]:
                findings.append(
                    f"conforming slice {slice_id} decision {decision['id']} requires evidence"
                )

    for decision in closure["realization_decisions"]:
        for authority_id in decision["authority_ids"]:
            if authority_id not in authority_by_id:
                findings.append(
                    f"closure decision {decision['id']} has unknown authority {authority_id}"
                )
        if not set(decision["evidence_refs"]).issubset(closure["evidence_refs"]):
            findings.append(
                f"closure decision {decision['id']} evidence must also be closure evidence"
            )
        if decision["implementation_status"] == "conforming" and not decision["evidence_refs"]:
            findings.append(f"conforming closure decision {decision['id']} requires evidence")

    findings.extend(_cycle_findings(slices))

    blocked_authority_ids = {
        authority_id
        for blocker in (
            campaign["campaign"]["blocker"],
            *(entry["blocker"] for entry in slice_entries),
        )
        if blocker is not None
        for authority_id in blocker["authority_ids"]
    }

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
        # An aggregate row is a roll-up of its contributors, and nothing else reconciles it. A
        # campaign that has run every contributor of a fully planned authority to completion has
        # nothing left to wait for, so a roll-up still reading unevaluated, absent, or partial
        # there understates finished work rather than describing it.
        #
        # Pausing is the one time saying "unfinished" is the honest thing to do — but "state the
        # exact disposition" means naming which authority, so a blocked or stale campaign gets
        # that latitude only where a blocker actually names the row. Anywhere else the
        # understatement is the same defect it would be while executing, and a paused record does
        # not become a place to quietly park settled work. Replanning is exempt outright: a
        # planning or awaiting-approval campaign has no blocker to name anything with, and newly
        # modelled authority has to go somewhere before anyone evaluates it. Partial planned
        # coverage is never settled by completion, because the plan never intended to close it.
        #
        # Overstatement is wrong in every lifecycle and gets no exemption at all, in either of its
        # two shapes: conforming while a contributor is still open, and conforming while a blocker
        # says that very authority is what the campaign stopped on.
        settled = bool(authority["slice_ids"]) and all(
            slice_id in slices and slices[slice_id]["lifecycle"] == "complete"
            for slice_id in authority["slice_ids"]
        )
        status = authority["implementation_status"]
        lifecycle = campaign["campaign"]["lifecycle"]
        unfinished = status in {"not evaluated", "absent", "partial"}
        if settled and unfinished and authority["planned_coverage"] == "full":
            if lifecycle in {"ready", "active", "complete"}:
                findings.append(
                    f"authority {authority_id} is {status} with every contributing slice complete"
                )
            elif lifecycle in {"blocked", "stale"} and authority_id not in blocked_authority_ids:
                findings.append(
                    f"authority {authority_id} is {status} with every contributing slice complete "
                    "and no blocker naming it"
                )
        if not settled and status == "conforming":
            findings.append(
                f"authority {authority_id} is conforming with an incomplete contributing slice"
            )
        if status == "conforming" and authority_id in blocked_authority_ids:
            findings.append(f"authority {authority_id} is conforming and blocked at the same time")

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
            for decision in entry["realization_decisions"]:
                if decision["implementation_status"] != "conforming":
                    findings.append(
                        f"complete slice {slice_id} decision {decision['id']} must be conforming"
                    )
                if not decision["evidence_refs"]:
                    findings.append(
                        f"complete slice {slice_id} decision {decision['id']} requires evidence"
                    )
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
        for decision in closure["realization_decisions"]:
            if decision["implementation_status"] != "conforming":
                findings.append(
                    f"a complete campaign requires closure decision {decision['id']} conforming"
                )
            if not decision["evidence_refs"]:
                findings.append(
                    f"a complete campaign requires closure decision {decision['id']} evidence"
                )
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
                **{
                    key: entry[key]
                    for key in (
                        "id",
                        "order",
                        "label",
                        "kind",
                        "dependencies",
                        "authority",
                        "verification_refs",
                    )
                },
                "realization_decisions": [
                    {
                        key: decision[key]
                        for key in (
                            "id",
                            "summary",
                            "authority_ids",
                            "reversible",
                            "evidence_intent",
                        )
                    }
                    for decision in entry["realization_decisions"]
                ],
            }
            for entry in campaign["slices"]
        ],
        "closure": {
            "authority_coverage": campaign["closure"]["authority_coverage"],
            "realization_decisions": [
                {
                    key: decision[key]
                    for key in (
                        "id",
                        "summary",
                        "authority_ids",
                        "reversible",
                        "evidence_intent",
                    )
                }
                for decision in campaign["closure"]["realization_decisions"]
            ],
        },
    }


def _git_succeeds(root: Path, *arguments: str) -> bool:
    completed = subprocess.run(  # noqa: S603
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _head_evidence_findings(campaign: dict[str, Any], *, root: Path) -> list[str]:
    findings: list[str] = []
    for label, reference in _all_evidence_references(campaign):
        if not reference.startswith("path:"):
            continue
        value = reference.removeprefix("path:")
        path, _, fragment = value.partition("#")
        try:
            source = _git(root, "show", f"HEAD:{path}")
        except RuntimeError:
            findings.append(f"{label} is not committed at HEAD: {path}")
            continue
        if not _evidence_fragment_exists(path, source, fragment):
            findings.append(f"{label} fragment does not resolve at HEAD: {path}#{fragment}")
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


def _retained_approval_findings(campaign: dict[str, Any], *, root: Path) -> list[str]:
    """Resolve the approval a blocked or stale campaign still rests on.

    Its own approval is cleared, so nothing in the record can say whether that sha names a
    reachable plan or one the campaign has already advanced past.
    """
    checkpoint = campaign["campaign"]["checkpoint"]
    match = APPROVAL_CHECKPOINT.fullmatch(checkpoint) if checkpoint is not None else None
    if match is None:
        return []
    retained = match.group("plan")
    if not _git_succeeds(root, "cat-file", "-e", f"{retained}^{{commit}}"):
        return [f"retained approval commit does not exist: {retained}"]
    if not _git_succeeds(root, "merge-base", "--is-ancestor", retained, "HEAD"):
        return [f"retained approval commit is not an ancestor of HEAD: {retained}"]
    try:
        planned = load_campaign_text(
            _git(root, "show", f"{retained}:implementation-campaign.yaml"),
            label=f"{retained}:implementation-campaign.yaml",
        )
    except (RuntimeError, ValueError, yaml.YAMLError) as error:
        return [f"retained approval campaign is unreadable: {error}"]
    inherited = {entry["id"] for entry in planned["slices"] if entry["lifecycle"] == "complete"}
    ahead = [
        entry["id"]
        for entry in campaign["slices"]
        if entry["lifecycle"] == "complete" and entry["id"] not in inherited
    ]
    if ahead:
        return [
            "retained approval predates completed slices: " + ", ".join(sorted(ahead)),
        ]
    return []


def checkpoint_binding_findings(campaign: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    """Bind the current campaign to ordinary committed recovery state.

    The repository owner, executing agent, Git implementation, and checker are trusted. This check
    detects accidental dirty state, stale approval, plan drift, and uncommitted evidence; it is not
    a tamper-resistant audit of historical Git objects.
    """
    findings: list[str] = []
    tracked_state = _git(root, "status", "--porcelain", "--untracked-files=no")
    if tracked_state:
        findings.append("checkpoint validation requires a clean tracked working tree and index")

    try:
        committed = load_campaign_text(
            _git(root, "show", "HEAD:implementation-campaign.yaml"),
            label="HEAD:implementation-campaign.yaml",
        )
    except (RuntimeError, ValueError, yaml.YAMLError) as error:
        return [*findings, f"HEAD has no readable implementation campaign: {error}"]
    if committed != campaign:
        findings.append("the working campaign does not match the campaign committed at HEAD")

    findings.extend(_head_evidence_findings(campaign, root=root))
    approval = campaign["campaign"]["plan_approval"]
    if approval["status"] != "accepted":
        # Blocking clears the approval but a campaign blocked after a renewal still rests on it.
        # The record can no longer resolve that sha, so check here that it names real recovery
        # state rather than a plan the campaign never reached.
        findings.extend(_retained_approval_findings(campaign, root=root))
        return findings

    checkpoint = approval["checkpoint"]
    match = APPROVAL_CHECKPOINT.fullmatch(checkpoint or "")
    if match is None:
        findings.append("accepted approval does not identify a valid approved plan commit")
        return findings
    plan_commit = match.group("plan")
    if not _git_succeeds(root, "cat-file", "-e", f"{plan_commit}^{{commit}}"):
        findings.append(f"approved plan commit does not exist: {plan_commit}")
        return findings
    if not _git_succeeds(root, "merge-base", "--is-ancestor", plan_commit, "HEAD"):
        findings.append(f"approved plan commit is not an ancestor of HEAD: {plan_commit}")
        return findings

    try:
        planned = load_campaign_text(
            _git(root, "show", f"{plan_commit}:implementation-campaign.yaml"),
            label=f"{plan_commit}:implementation-campaign.yaml",
        )
    except (RuntimeError, ValueError, yaml.YAMLError) as error:
        findings.append(f"approved plan campaign is unreadable: {error}")
        return findings
    if _plan_projection(campaign) != _plan_projection(planned):
        findings.append("current campaign changed plan-bearing content after approval")

    # The approved plan's own record says which slices were already complete when it was reviewed.
    # That is the boundary the working record cannot supply: everything finished since then belongs
    # to this plan and must say so, and everything finished before it keeps the label it earned.
    inherited = {
        entry["id"]: entry["checkpoint"]
        for entry in planned["slices"]
        if entry["lifecycle"] == "complete"
    }
    for entry in campaign["slices"]:
        if entry["lifecycle"] != "complete" or entry["checkpoint"] is None:
            continue
        if entry["id"] not in inherited:
            slice_match = SLICE_CHECKPOINT.fullmatch(entry["checkpoint"])
            if slice_match is not None and slice_match.group("plan") != plan_commit[:12]:
                findings.append(
                    f"slice {entry['id']} completed under this approval but checkpoints "
                    "against a superseded plan"
                )
        elif entry["checkpoint"] != inherited[entry["id"]]:
            findings.append(
                f"slice {entry['id']} completed before this approval and may not be re-minted"
            )

    # An approval commit — first or renewed after a replan — is the state in which the approval is
    # itself the campaign checkpoint. A commit that also completes a slice still claims that state,
    # so it is judged by these rules rather than escaping them. Which commit granted the approval is
    # read from what changed, not from fields the commit writes about itself: a commit claiming a
    # different lifecycle would otherwise decline the very rules that bound it, and an ordinary
    # commit landing while the campaign rests on its approval would be judged as one.
    parents = _git(root, "rev-list", "--parents", "-n", "1", "HEAD").split()
    granted = approval
    if len(parents) == 2:
        try:
            granted = load_campaign_text(
                _git(root, "show", f"{parents[1]}:implementation-campaign.yaml"),
                label=f"{parents[1]}:implementation-campaign.yaml",
            )["campaign"]["plan_approval"]
        except RuntimeError, ValueError, yaml.YAMLError, KeyError:
            granted = None
    if granted != approval:
        if len(parents) != 2 or parents[1] != plan_commit:
            findings.append("the approval commit must directly follow its approved plan")
        changed_paths = set(
            _git(
                root,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "HEAD",
            ).splitlines()
        )
        if changed_paths != {"implementation-campaign.yaml"}:
            findings.append("the approval commit must change only the campaign record")
        if committed != _expected_approval_campaign(planned, checkpoint=checkpoint):
            findings.append("the approval commit contains changes beyond approval state")
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
    open_decisions = [
        f"{decision['id']}@{entry['id']}"
        for entry in slice_entries
        for decision in entry["realization_decisions"]
        if decision["implementation_status"] != "conforming"
    ]
    open_decisions.extend(
        f"{decision['id']}@closure"
        for decision in campaign["closure"]["realization_decisions"]
        if decision["implementation_status"] != "conforming"
    )
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
        "Open decisions: " + (", ".join(open_decisions) if open_decisions else "none"),
        (
            "Closure: authority="
            f"{campaign['closure']['authority_coverage']}, "
            f"integration={campaign['closure']['integration_status']}, "
            f"runnable={campaign['closure']['runnable_status']}"
        ),
        f"Checkpoint: {campaign['campaign']['checkpoint'] or 'none'}",
    ]
    return "\n".join(lines)


def _worktree_condition(root: Path) -> dict[str, Any]:
    all_changes = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = [entry for entry in all_changes.split("\0") if entry]
    tracked_changes = _git(root, "status", "--porcelain", "--untracked-files=no")
    digest = hashlib.sha256()
    digest.update(all_changes.encode("utf-8"))
    digest.update(_git(root, "diff", "--binary").encode("utf-8"))
    digest.update(_git(root, "diff", "--cached", "--binary").encode("utf-8"))
    for entry in entries:
        if not entry.startswith("?? "):
            continue
        path = root / entry[3:]
        if path.is_symlink():
            digest.update(str(path.readlink()).encode("utf-8"))
        elif path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    return {
        "status": "dirty" if all_changes else "clean",
        "tracked_changes": bool(tracked_changes),
        "untracked_changes": any(entry.startswith("?? ") for entry in entries),
        "fingerprint": digest.hexdigest(),
    }


def _state_token(campaign: dict[str, Any], *, root: Path, worktree: dict[str, Any]) -> str:
    active = next(
        (entry["id"] for entry in campaign["slices"] if entry["lifecycle"] == "active"),
        None,
    )
    ready = sorted(
        (entry["order"], entry["id"])
        for entry in campaign["slices"]
        if entry["lifecycle"] == "ready"
    )
    identity = {
        "head": _git(root, "rev-parse", "HEAD"),
        "branch": _git(root, "branch", "--show-current") or None,
        "campaign_id": campaign["campaign"]["id"],
        "lifecycle": campaign["campaign"]["lifecycle"],
        "checkpoint": campaign["campaign"]["checkpoint"],
        "active": active,
        "ready": ready,
        "worktree": worktree,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def dispatch_packet(
    campaign: dict[str, Any],
    *,
    root: Path = ROOT,
    validation_findings: list[str] | None = None,
    identical_failures: int = 0,
) -> dict[str, Any]:
    """Return one deterministic manager disposition without mutating campaign state."""
    findings = list(validation_findings or [])
    worktree = _worktree_condition(root)
    active = next((entry for entry in campaign["slices"] if entry["lifecycle"] == "active"), None)
    ready = min(
        (entry for entry in campaign["slices"] if entry["lifecycle"] == "ready"),
        key=lambda entry: entry["order"],
        default=None,
    )
    all_slices_complete = all(entry["lifecycle"] == "complete" for entry in campaign["slices"])

    action = "stop-invalid"
    work_item: str | None = None
    reason_codes: list[str] = []
    if findings:
        reason_codes.append("validation-failed")
    elif worktree["status"] == "clean":
        findings.extend(checkpoint_binding_findings(campaign, root=root))
        if findings:
            reason_codes.append("checkpoint-validation-failed")

    if not findings:
        lifecycle = campaign["campaign"]["lifecycle"]
        approval = campaign["campaign"]["plan_approval"]["status"]
        baseline = campaign["model_baseline"]["status"]
        if active is not None:
            action = "resume-slice"
            work_item = active["id"]
            reason_codes.append(
                "active-slice-has-working-state"
                if worktree["status"] == "dirty"
                else "active-slice-interrupted"
            )
        elif worktree["status"] == "dirty":
            action = "stop-dirty"
            reason_codes.append("dirty-state-has-no-active-slice")
        elif lifecycle == "complete":
            action = "complete"
            work_item = CLOSURE_WORK_ITEM
            reason_codes.append("campaign-complete")
        elif (
            approval != "accepted"
            or baseline != "current"
            or lifecycle
            in {
                "awaiting-plan-approval",
                "blocked",
                "stale",
            }
        ):
            action = "await-human"
            if approval != "accepted":
                reason_codes.append("approval-required")
            if baseline != "current":
                reason_codes.append("baseline-not-current")
            if lifecycle in {"blocked", "stale"}:
                reason_codes.append("campaign-blocked")
        elif ready is not None:
            action = "launch-slice"
            work_item = ready["id"]
            reason_codes.append("dependency-ready-slice")
        elif all_slices_complete:
            action = "launch-closure"
            work_item = CLOSURE_WORK_ITEM
            reason_codes.append("all-slices-complete")
        else:
            findings.append(
                "campaign has no active, ready, blocked, complete, or closure-ready work"
            )
            reason_codes.append("no-dispatchable-state")

    token = _state_token(campaign, root=root, worktree=worktree)
    if action in {"launch-slice", "resume-slice", "launch-closure"} and identical_failures >= 3:
        action = "await-human"
        reason_codes.append("identical-failure-limit-reached")

    return {
        "schema_version": 1,
        "campaign_id": campaign["campaign"]["id"],
        "git": {
            "branch": _git(root, "branch", "--show-current") or None,
            "head": _git(root, "rev-parse", "HEAD"),
        },
        "worktree": worktree,
        "checkpoint": campaign["campaign"]["checkpoint"],
        "state_token": token,
        "action": action,
        "work_item": work_item,
        "reason_codes": reason_codes,
        "errors": findings,
    }


def _closure_review_frame(campaign: dict[str, Any], *, lens: str, state_token: str) -> str:
    """Frame the whole-system closure item rather than one slice.

    Closure has no slice row to read, so its frame is the aggregate: every authority entry
    with its rolled-up status, the three closure dimensions, and whatever blocker the
    campaign is resting on. It stays finding-free for the same reason a slice frame does.
    """
    if any(entry["lifecycle"] != "complete" for entry in campaign["slices"]):
        raise ValueError("review frame requires every slice complete: closure")

    authority_lines = [
        f"- {entry['id']} {entry['label']}: planned {entry['planned_coverage']}; "
        f"status {entry['implementation_status']}; slices: " + ", ".join(entry["slice_ids"])
        for entry in campaign["authority"]
    ]
    closure = campaign["closure"]
    evidence_lines = [f"- {reference}" for reference in closure["evidence_refs"]] or ["- none"]
    # A recorded blocker carries the closure writer's own diagnosis and prescribed resolution, and
    # handing that prose to both lenses is exactly the prior finding a fixed frame excludes. Its
    # classification and the authority it names are state a reviewer needs; the summary is not.
    blocker = campaign["campaign"]["blocker"]
    blocker_lines = (
        [
            f"- classification: {blocker['classification']}",
            "- authority: " + (", ".join(blocker["authority_ids"]) or "none"),
        ]
        if blocker is not None
        else ["- none"]
    )
    inherited_decision_lines = [
        f"- {decision['id']} ({decision['implementation_status']}): {decision['summary']}"
        for entry in campaign["slices"]
        for decision in entry["realization_decisions"]
    ] or ["- none"]
    owned_decision_lines = [
        f"- {decision['id']} ({decision['implementation_status']}): {decision['summary']}"
        for decision in closure["realization_decisions"]
    ] or ["- none"]
    decision_evidence_lines = [
        f"- {decision['id']}: {reference}"
        for decision in closure["realization_decisions"]
        for reference in decision["evidence_refs"]
    ] or ["- none"]
    decision_intent_lines = [
        f"- {decision['id']}: {intent}"
        for decision in closure["realization_decisions"]
        for intent in decision["evidence_intent"]
    ] or ["- none"]
    lens_task = {
        "authority": (
            "Trace whether the aggregate authority universe is complete against the current "
            "model, whether every rolled-up status and coverage claim is true of the work "
            "actually finished, and whether any genuine model or plan gap remains open."
        ),
        "engineering": (
            "Inspect whether integration across slices holds, whether the closure evidence "
            "discriminates the nearest wrong result, whether the runnable-boundary and "
            "documentation claims match what a cold reader can reproduce, and whether any "
            "obsolete scaffolding or unsupported capability claim survives."
        ),
    }[lens]
    return "\n".join(
        [
            f"# Read-only {lens} review for closure",
            "",
            f"Review state token: {state_token}",
            "Return this exact token with your disposition.",
            "",
            "Work independently from the current workspace. Read and obey AGENTS.md and the named",
            "complete authored model sources. Do not mutate files, inspect protected user data, or",
            "assume conversation history. Treat local repository and checkpoint machinery as",
            "trusted unless closure intentionally changes it.",
            "",
            "Work item: whole-system closure after the last planned slice",
            f"Campaign lifecycle: {campaign['campaign']['lifecycle']}",
            f"Model baseline status: {campaign['model_baseline']['status']}",
            f"Campaign checkpoint: {campaign['campaign']['checkpoint'] or 'none'}",
            "",
            "## Lens",
            "",
            lens_task,
            "",
            "## Aggregate authority and rolled-up status",
            "",
            *authority_lines,
            "",
            "## Closure dimensions",
            "",
            f"- authority coverage: {closure['authority_coverage']}",
            f"- integration status: {closure['integration_status']}",
            f"- runnable status: {closure['runnable_status']}",
            f"- closure checkpoint: {closure['checkpoint'] or 'none'}",
            "",
            "## Decisions already closed by slices and preserved at closure",
            "",
            *inherited_decision_lines,
            "",
            "## Decisions closure must close",
            "",
            *owned_decision_lines,
            "",
            "## Decision-attributable closure evidence",
            "",
            *decision_evidence_lines,
            "",
            "## Planned decision evidence intent",
            "",
            *decision_intent_lines,
            "",
            "## Recorded campaign blocker",
            "",
            *blocker_lines,
            "",
            "## Current closure evidence",
            "",
            *evidence_lines,
            "",
            "## Materiality and response",
            "",
            "Report a material finding only when it names a plausible consequence within the",
            "qualified authority, selected boundaries, declared project assumptions, or ordinary",
            "malformed-input and recovery behavior. Do not invent novel mutants, fuzz spaces,",
            "attack models, or speculative inputs merely to find something new.",
            "Style preferences, alternate truthful wording, duplicated evidence, and unselected",
            "hardening are optional observations and do not make the review non-clean.",
            "",
            "Return complete material findings first. Give each consequence and reproducible",
            "evidence, then optional observations. Disposition every decision closure owns;",
            "aggregate authority or nearby evidence does not substitute for decision evidence.",
            "Say explicitly when no material findings exist.",
        ]
    )


def review_frame(campaign: dict[str, Any], *, slice_id: str, lens: str, state_token: str) -> str:
    """Build a project-bound, finding-free prompt for one read-only review lens.

    Dispatch names two kinds of work item, so this names the same two. ``closure`` is the
    whole-system item that follows the last slice; every other value is a slice ID.
    """
    if lens not in REVIEW_LENSES:
        raise ValueError(f"unknown review lens: {lens}")
    if re.fullmatch(r"[0-9a-f]{64}", state_token) is None:
        raise ValueError("review frame requires a 64-character lowercase hexadecimal state token")
    if slice_id == CLOSURE_WORK_ITEM:
        return _closure_review_frame(campaign, lens=lens, state_token=state_token)
    try:
        selected = next(entry for entry in campaign["slices"] if entry["id"] == slice_id)
    except StopIteration as error:
        raise ValueError(f"unknown campaign slice: {slice_id}") from error
    if selected["lifecycle"] != "active":
        raise ValueError(f"review frame requires an active slice: {slice_id}")

    authority_by_id = {entry["id"]: entry for entry in campaign["authority"]}
    authority_lines: list[str] = []
    for contribution in selected["authority"]:
        authority = authority_by_id[contribution["authority_id"]]
        remainder = ", ".join(contribution["remaining_slice_ids"]) or "none"
        authority_lines.append(
            f"- {authority['id']} {authority['label']}: {contribution['coverage']}; "
            f"remaining slices: {remainder}"
        )
        authority_lines.extend(
            f"  - {reference['model_ref']} ({reference['source']})"
            for reference in authority["refs"]
        )

    owned_decision_lines = [
        f"- {decision['id']} ({decision['implementation_status']}): {decision['summary']}"
        for decision in selected["realization_decisions"]
    ] or ["- none"]
    decision_evidence_lines = [
        f"- {decision['id']}: {reference}"
        for decision in selected["realization_decisions"]
        for reference in decision["evidence_refs"]
    ] or ["- none"]
    decision_intent_lines = [
        f"- {decision['id']}: {intent}"
        for decision in selected["realization_decisions"]
        for intent in decision["evidence_intent"]
    ] or ["- none"]
    slices = {entry["id"]: entry for entry in campaign["slices"]}
    inherited_ids: set[str] = set()
    frontier = list(selected["dependencies"])
    while frontier:
        dependency_id = frontier.pop()
        if dependency_id in inherited_ids:
            continue
        inherited_ids.add(dependency_id)
        frontier.extend(slices[dependency_id]["dependencies"])
    inherited_decision_lines = [
        f"- {decision['id']} ({decision['implementation_status']} from {entry['id']}): "
        f"{decision['summary']}"
        for entry in campaign["slices"]
        if entry["id"] in inherited_ids
        for decision in entry["realization_decisions"]
    ] or ["- none"]
    closure_decision_lines = [
        f"- {decision['id']} ({decision['implementation_status']}): {decision['summary']}"
        for decision in campaign["closure"]["realization_decisions"]
        if decision["implementation_status"] != "conforming"
    ] or ["- none"]
    evidence_lines = [f"- {reference}" for reference in selected["evidence_refs"]] or ["- none"]
    verification_lines = [f"- {reference}" for reference in selected["verification_refs"]] or [
        "- none"
    ]
    dependency_lines = [f"- {dependency}" for dependency in selected["dependencies"]] or ["- none"]

    lens_task = {
        "authority": (
            "Trace qualified model meaning, slice scope, dependencies, full/partial coverage, "
            "promised outcomes and non-effects, and whether any genuine model or plan gap remains."
        ),
        "engineering": (
            "Inspect implementation correctness, declared input and failure boundaries, evidence "
            "discrimination, applicable numerical/temporal/recovery behavior, and unnecessary "
            "realization machinery."
        ),
    }[lens]
    return "\n".join(
        [
            f"# Read-only {lens} review for {slice_id}",
            "",
            f"Review state token: {state_token}",
            "Return this exact token with your disposition.",
            "",
            "Work independently from the current workspace. Read and obey AGENTS.md and the named",
            "qualified model sources and their transitive semantic dependencies. Do not mutate",
            "files, inspect protected user data, or assume",
            "conversation history. Treat local repository and checkpoint machinery as trusted",
            "unless the slice intentionally changes it.",
            "",
            f"Slice: {selected['label']} ({selected['kind']})",
            f"Model baseline status: {campaign['model_baseline']['status']}",
            f"Campaign checkpoint: {campaign['campaign']['checkpoint'] or 'none'}",
            "",
            "## Lens",
            "",
            lens_task,
            "",
            "## Dependencies",
            "",
            *dependency_lines,
            "",
            "## Qualified authority and coverage",
            "",
            *authority_lines,
            "",
            "## Verification references",
            "",
            *verification_lines,
            "",
            "## Decisions this slice must close",
            "",
            *owned_decision_lines,
            "",
            "## Decision-attributable evidence",
            "",
            *decision_evidence_lines,
            "",
            "## Planned decision evidence intent",
            "",
            *decision_intent_lines,
            "",
            "## Inherited decisions this slice must preserve",
            "",
            *inherited_decision_lines,
            "",
            "## Closure decisions still awaiting execution",
            "",
            *closure_decision_lines,
            "",
            "## Current campaign evidence",
            "",
            *evidence_lines,
            "",
            "## Materiality and response",
            "",
            "Report a material finding only when it names a plausible consequence within the",
            "qualified authority, selected boundaries, declared project assumptions, or ordinary",
            "malformed-input and recovery behavior. Do not invent novel mutants, fuzz spaces,",
            "attack models, or speculative inputs merely to find something new.",
            "Style preferences, alternate truthful wording, duplicated evidence, and unselected",
            "hardening are optional observations and do not make the review non-clean.",
            "",
            "Return complete material findings first. Give each consequence and reproducible",
            "evidence, then optional observations. Disposition every decision this slice owns;",
            "aggregate authority or nearby evidence does not substitute for decision evidence.",
            "Say explicitly when no material findings exist.",
        ]
    )


def worker_result_findings(
    result: Any,
    *,
    expected_state_token: str | None = None,
    current_state_token: str | None = None,
    expected_campaign_id: str | None = None,
    expected_work_item: str | None = None,
    expected_checkpoint: str | None = None,
    approved_plan_sha: str | None = None,
) -> list[str]:
    schema = _schema(WORKER_RESULT_SCHEMA_PATH)
    findings = [
        f"{_json_path(error.absolute_path)}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(result),
            key=lambda error: (list(error.absolute_path), error.message),
        )
    ]
    if isinstance(result, dict):
        outcome = result.get("outcome")
        review_state_token = result.get("review_state_token")
        reviews = result.get("reviews")
        if outcome == "checkpointed":
            if result.get("campaign_id") != expected_campaign_id:
                findings.append("campaign_id does not match the current campaign")
            if result.get("work_item") != expected_work_item:
                findings.append("work_item does not match the current campaign work item")
            if result.get("checkpoint") != expected_checkpoint:
                findings.append("checkpoint does not match the intended checkpoint")
            checkpoint = result.get("checkpoint")
            if approved_plan_sha is None:
                findings.append("checkpointed result requires a valid approved plan checkpoint")
            elif isinstance(checkpoint, str):
                if expected_work_item == CLOSURE_WORK_ITEM:
                    match = CLOSURE_CHECKPOINT.fullmatch(checkpoint)
                    valid_checkpoint = (
                        match is not None and match.group("plan") == approved_plan_sha[:12]
                    )
                else:
                    match = SLICE_CHECKPOINT.fullmatch(checkpoint)
                    valid_checkpoint = (
                        match is not None
                        and match.group("slice") == expected_work_item
                        and match.group("plan") == approved_plan_sha[:12]
                    )
                if not valid_checkpoint:
                    findings.append(
                        "checkpoint does not match the work item and approved plan format"
                    )
            if any(
                not isinstance(check, dict) or check.get("outcome") != "passed"
                for check in result.get("checks", [])
            ):
                findings.append("checkpointed result requires every reported check passed")
            if expected_state_token is None:
                findings.append("checkpointed result requires the expected frozen state token")
            elif review_state_token != expected_state_token:
                findings.append("review_state_token does not match the expected frozen state")
            if current_state_token is not None and review_state_token != current_state_token:
                findings.append("review_state_token does not match the current durable state")
        if outcome == "checkpointed" and isinstance(reviews, list):
            valid_reviews = [item for item in reviews if isinstance(item, dict)]
            lenses = [item.get("lens") for item in valid_reviews]
            reviewers = [item.get("reviewer") for item in valid_reviews]
            tokens = [item.get("state_token") for item in valid_reviews]
            statuses = [item.get("status") for item in valid_reviews]
            if sorted(lens for lens in lenses if isinstance(lens, str)) != list(REVIEW_LENSES):
                findings.append(
                    "checkpointed result requires distinct authority and engineering reviews"
                )
            if len(set(reviewer for reviewer in reviewers if isinstance(reviewer, str))) != 2:
                findings.append("checkpointed result requires two distinct reviewer identities")
            if any(status != "clean" for status in statuses):
                findings.append("checkpointed result requires both final reviews clean")
            if any(token != review_state_token for token in tokens):
                findings.append("final review tokens must equal review_state_token")
        review_pairs = result.get("review_pairs")
        material_findings = result.get("material_findings")
        if isinstance(review_pairs, int) and isinstance(material_findings, list):
            pairs: list[int] = []
            for item in material_findings:
                if not isinstance(item, dict):
                    continue
                pair = item.get("pair")
                if isinstance(pair, int):
                    pairs.append(pair)
            if pairs and max(pairs) > review_pairs:
                findings.append("material_findings names a pair beyond review_pairs")
            if len(material_findings) != review_pairs:
                findings.append("material_findings must report counts for every review pair")
            if pairs and sorted(pairs) != list(range(1, review_pairs + 1)):
                findings.append("material_findings pair numbers must be unique and contiguous")
            if outcome == "checkpointed" and material_findings:
                final_counts = next(
                    (
                        item
                        for item in material_findings
                        if isinstance(item, dict) and item.get("pair") == review_pairs
                    ),
                    None,
                )
                if isinstance(final_counts, dict) and any(
                    final_counts.get(lens) != 0 for lens in REVIEW_LENSES
                ):
                    findings.append(
                        "checkpointed result requires zero material findings in the final pair"
                    )
    return findings


def checkpointable_work_item(campaign: dict[str, Any]) -> str | None:
    """Return only the slice or closure item whose reviewed checkpoint can advance now."""
    active = [item["id"] for item in campaign["slices"] if item["lifecycle"] == "active"]
    if len(active) == 1:
        return active[0]
    if (
        not active
        and campaign["campaign"]["lifecycle"] == "active"
        and all(item["lifecycle"] == "complete" for item in campaign["slices"])
    ):
        return CLOSURE_WORK_ITEM
    return None


def _unreadable_dispatch_packet(error: Exception, *, root: Path = ROOT) -> dict[str, Any]:
    worktree = _worktree_condition(root)
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current") or None
    identity = json.dumps(
        {"head": head, "branch": branch, "worktree": worktree},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "campaign_id": None,
        "git": {"branch": branch, "head": head},
        "worktree": worktree,
        "checkpoint": None,
        "state_token": hashlib.sha256(identity).hexdigest(),
        "action": "stop-invalid",
        "work_item": None,
        "reason_codes": ["campaign-unreadable"],
        "errors": [str(error)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect the implementation campaign")
    parser.add_argument(
        "command",
        choices=(
            "check",
            "status",
            "baseline",
            "checkpoint-check",
            "dispatch",
            "review-frame",
            "worker-result-check",
        ),
    )
    parser.add_argument(
        "--campaign",
        type=Path,
        default=IMPLEMENTATION_CAMPAIGN_PATH,
        help="campaign YAML path",
    )
    parser.add_argument("--slice", help=f"slice ID, or {CLOSURE_WORK_ITEM!r}, for review-frame")
    parser.add_argument("--lens", choices=REVIEW_LENSES, help="review-frame lens")
    parser.add_argument("--result", type=Path, help="worker result JSON path")
    parser.add_argument("--expect-checkpoint", help="intended checkpoint for worker-result-check")
    parser.add_argument(
        "--expect-state-token",
        help="reject a dispatch if durable state no longer matches this token",
    )
    parser.add_argument(
        "--identical-failures",
        type=int,
        default=0,
        help="consecutive launcher failures against the current state token",
    )
    arguments = parser.parse_args()

    if arguments.command == "baseline":
        print(yaml.safe_dump(observed_baseline(), sort_keys=True).strip())
        return 0

    if arguments.command == "worker-result-check":
        if arguments.result is None:
            parser.error("worker-result-check requires --result")
        if arguments.expect_state_token is None:
            parser.error("worker-result-check requires --expect-state-token")
        if arguments.expect_checkpoint is None:
            parser.error("worker-result-check requires --expect-checkpoint")
        try:
            campaign = load_campaign(arguments.campaign)
            campaign_findings = validate_campaign(campaign)
            if not campaign_findings:
                campaign_findings.extend(qualified_model_reference_findings(campaign))
            if campaign_findings:
                for finding in campaign_findings:
                    print(f"ERROR {finding}")
                return 1
            worktree = _worktree_condition(arguments.campaign.parent)
            current_state_token = _state_token(
                campaign, root=arguments.campaign.parent, worktree=worktree
            )
            result = json.loads(arguments.result.read_text(encoding="utf-8"))
            expected_work_item = checkpointable_work_item(campaign)
            if expected_work_item is None:
                print("ERROR campaign has no checkpointable active slice or closure item")
                return 1
            approval = APPROVAL_CHECKPOINT.fullmatch(
                campaign["campaign"]["plan_approval"]["checkpoint"] or ""
            )
            result_findings = worker_result_findings(
                result,
                expected_state_token=arguments.expect_state_token,
                current_state_token=current_state_token,
                expected_campaign_id=campaign["campaign"]["id"],
                expected_work_item=expected_work_item,
                expected_checkpoint=arguments.expect_checkpoint,
                approved_plan_sha=approval.group("plan") if approval is not None else None,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"ERROR {error}")
            return 1
        if result_findings:
            for finding in result_findings:
                print(f"ERROR {finding}")
            return 1
        print("Implementation campaign worker result is valid.")
        return 0

    try:
        campaign = load_campaign(arguments.campaign)
        findings = validate_campaign(campaign)
        if not findings:
            findings.extend(qualified_model_reference_findings(campaign))
        if not findings and arguments.command == "checkpoint-check":
            findings.extend(checkpoint_binding_findings(campaign))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        if arguments.command == "dispatch":
            print(json.dumps(_unreadable_dispatch_packet(error), indent=2, sort_keys=True))
            return 1
        print(f"ERROR {error}")
        return 1

    if arguments.command == "dispatch":
        packet = dispatch_packet(
            campaign,
            validation_findings=findings,
            identical_failures=arguments.identical_failures,
        )
        expected = arguments.expect_state_token
        if expected is not None and expected != packet["state_token"]:
            packet["action"] = "stop-invalid"
            packet["reason_codes"].append("stale-dispatch-token")
            packet["errors"].append("durable state changed after dispatch")
        print(json.dumps(packet, indent=2, sort_keys=True))
        return 1 if packet["action"] == "stop-invalid" else 0

    if findings:
        for finding in findings:
            print(f"ERROR {finding}")
        return 1
    if arguments.command == "review-frame":
        if arguments.slice is None or arguments.lens is None:
            parser.error("review-frame requires --slice and --lens")
        try:
            worktree = _worktree_condition(arguments.campaign.parent)
            state_token = _state_token(campaign, root=arguments.campaign.parent, worktree=worktree)
            print(
                review_frame(
                    campaign,
                    slice_id=arguments.slice,
                    lens=arguments.lens,
                    state_token=state_token,
                )
            )
        except ValueError as error:
            print(f"ERROR {error}")
            return 1
    elif arguments.command == "status":
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
