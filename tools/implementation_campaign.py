from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator

try:
    from .model_layout import (
        IMPLEMENTATION_CAMPAIGN_PATH,
        IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH,
        ROOT,
    )
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import (  # type: ignore[no-redef]
        IMPLEMENTATION_CAMPAIGN_PATH,
        IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH,
        ROOT,
    )


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
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)  # noqa: S506
    if not isinstance(value, dict):
        raise ValueError(f"{path}: campaign must be a YAML mapping")
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
    parser.add_argument("command", choices=("check", "status", "baseline"))
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
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        print(f"ERROR {error}")
        return 1

    if findings:
        for finding in findings:
            print(f"ERROR {finding}")
        return 1
    if arguments.command == "status":
        print(_status(campaign))
    else:
        print(
            f"Implementation campaign is valid for {len(campaign['authority'])} authority entries "
            f"and {len(campaign['slices'])} slices."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
