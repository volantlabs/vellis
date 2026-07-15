from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from components.rtg.graph.protocol import JsonObject, RtgGraphSnapshot
from tools.repo_twin.model import Finding, ScanResult, produced_at_timestamp
from tools.repo_twin.scanner import component_subject_hashes
from tools.repo_twin.store import current_snapshot, plan_sync, snapshot_loaded


def evaluate_findings(
    scan: ScanResult,
    storage_root: Path,
    *,
    include_staleness: bool = True,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    snapshot: RtgGraphSnapshot | None = None
    if include_staleness:
        if not snapshot_loaded(storage_root):
            findings.append(
                Finding(
                    "stale_graph",
                    "error",
                    "repo",
                    "No synced repo twin snapshot exists.",
                    "Run `just graph-sync`.",
                )
            )
        else:
            snapshot = current_snapshot(storage_root)
            summary, _changes = plan_sync(scan, snapshot, materialize_changes=False)
            if summary.changed:
                findings.append(
                    Finding(
                        "stale_graph",
                        "error",
                        "repo",
                        (
                            "Repo twin differs from the working tree "
                            f"({summary.created} create, {summary.updated} update, "
                            f"{summary.pruned} prune)."
                        ),
                        "Run `just graph-sync`.",
                    )
                )
    elif snapshot_loaded(storage_root):
        snapshot = current_snapshot(storage_root)

    for issue in scan.parse_issues:
        findings.append(
            Finding(
                "parse_error",
                "error",
                issue.source_path,
                issue.message,
                "Fix the source file so the importer can parse it deterministically.",
            )
        )

    for component_id, paths in scan.duplicate_component_ids.items():
        findings.append(
            Finding(
                "duplicate_component_id",
                "error",
                component_id,
                f"Component ID appears in {', '.join(paths)}.",
                "Keep exactly one canonical component model per component ID.",
            )
        )

    declared_roots = {
        code_root
        for component in scan.components.values()
        for code_root in component.declared_code_roots
    }
    for component in scan.components.values():
        existing_roots = [
            code_root
            for code_root in component.declared_code_roots
            if code_root in scan.implementation_roots
        ]
        for code_root in component.declared_code_roots:
            if code_root not in scan.implementation_roots:
                accepted = component.status == "accepted"
                findings.append(
                    Finding(
                        "orphan_spec",
                        "error" if accepted else "warn",
                        component.component_id,
                        f"Declared code root does not exist: {code_root}.",
                        "Create the implementation root or update its realization binding.",
                    )
                )
        if not existing_roots:
            accepted = component.status == "accepted"
            findings.append(
                Finding(
                    "missing_implementation",
                    "error" if accepted else "warn",
                    component.component_id,
                    "Component has no existing implementation root.",
                    "Create an implementation root or keep the component in draft.",
                )
            )

    for root_path, implementation in scan.implementation_roots.items():
        if root_path not in declared_roots:
            findings.append(
                Finding(
                    "orphan_code_root",
                    "error",
                    root_path,
                    "Implementation root is not declared by any component spec.",
                    "Add the root to the owning model realization binding or move/remove the code.",
                )
            )
        owning_components = [
            component
            for component in scan.components.values()
            if root_path in component.declared_code_roots
        ]
        accepted_owner = any(component.status == "accepted" for component in owning_components)
        if not implementation.has_tests or not implementation.test_file_names:
            findings.append(
                Finding(
                    "missing_tests",
                    "error" if accepted_owner else "warn",
                    root_path,
                    "Implementation root has no populated tests directory.",
                    "Add boundary tests for the implementation root.",
                )
            )

    if snapshot is not None:
        findings.extend(_evidence_findings(scan, snapshot))

    return tuple(
        sorted(
            findings,
            key=lambda item: (item.severity != "error", item.finding_id, item.subject),
        )
    )


def has_errors(findings: tuple[Finding, ...]) -> bool:
    return any(finding.severity == "error" for finding in findings)


def _evidence_findings(scan: ScanResult, snapshot: RtgGraphSnapshot) -> list[Finding]:
    evidence_by_component = _passing_evidence_by_component(snapshot)
    findings: list[Finding] = []
    for component in scan.components.values():
        impl = next(
            (
                scan.implementation_roots[root]
                for root in component.declared_code_roots
                if root in scan.implementation_roots
            ),
            None,
        )
        if impl is None:
            continue
        current_hashes = component_subject_hashes(component, impl)
        evidence = evidence_by_component.get(component.component_id)
        if evidence is None:
            findings.append(
                Finding(
                    "missing_evidence",
                    "warn",
                    component.component_id,
                    "No passing test_run evidence matches this component.",
                    (
                        "Run a wrapped test command, for example "
                        "`just graph-evidence test_run just test`."
                    ),
                )
            )
            continue
        subject_hashes = evidence.get("subject_hashes")
        if isinstance(subject_hashes, str):
            try:
                subject_hashes = json.loads(subject_hashes)
            except json.JSONDecodeError:
                subject_hashes = None
        if not isinstance(subject_hashes, dict):
            continue
        if any(subject_hashes.get(key) != value for key, value in current_hashes.items()):
            findings.append(
                Finding(
                    "changed_contract",
                    "warn",
                    component.component_id,
                    (
                        "Modeled public contract or implementation hash changed since the newest "
                        "passing evidence."
                    ),
                    "Run a wrapped test command to refresh evidence after reviewing the change.",
                )
            )
    return findings


def _passing_evidence_by_component(snapshot: RtgGraphSnapshot) -> dict[str, JsonObject]:
    # Newest passing evidence wins, ordered by (parsed produced_at, record
    # UUID). produced_at carries microsecond precision for new records, so the
    # UUID only decides exact-timestamp ties; it is arbitrary but stable and
    # independent of snapshot iteration order.
    data_by_uuid = {
        str(item["uuid"]): item
        for item in snapshot.data_objects
        if item.get("type") == "twin.EvidenceRecord"
    }
    component_by_uuid = _component_ids_by_uuid(snapshot)
    best: dict[str, tuple[datetime, str]] = {}
    result: dict[str, JsonObject] = {}
    for anchor_uuid, data_uuids in snapshot.anchor_data_index.items():
        component_id = component_by_uuid.get(anchor_uuid)
        if component_id is None:
            continue
        for data_uuid in data_uuids:
            record = data_by_uuid.get(data_uuid)
            if record is None:
                continue
            properties = record.get("properties")
            if not isinstance(properties, dict):
                continue
            if properties.get("kind") != "test_run" or properties.get("passed") is not True:
                continue
            candidate = (produced_at_timestamp(properties), data_uuid)
            current = best.get(component_id)
            if current is None or candidate > current:
                best[component_id] = candidate
                result[component_id] = properties
    return result


def _component_ids_by_uuid(snapshot: RtgGraphSnapshot) -> dict[str, str]:
    components = {
        str(item["uuid"]): item for item in snapshot.anchors if item.get("type") == "twin.Component"
    }
    result: dict[str, str] = {}
    facts = {
        str(item["uuid"]): item
        for item in snapshot.data_objects
        if item.get("type") == "twin.ComponentFact"
    }
    for anchor_uuid, data_uuids in snapshot.anchor_data_index.items():
        if anchor_uuid not in components:
            continue
        for data_uuid in data_uuids:
            fact = facts.get(data_uuid)
            if fact is None:
                continue
            properties = fact.get("properties")
            if isinstance(properties, dict) and isinstance(properties.get("component_id"), str):
                component_id = properties["component_id"]
                if isinstance(component_id, str):
                    result[anchor_uuid] = component_id
    return result
