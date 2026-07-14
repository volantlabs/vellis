from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from components.rtg.graph.protocol import JsonObject
from tools.repo_twin.check import evaluate_findings
from tools.repo_twin.model import Finding, ScanResult
from tools.repo_twin.store import current_snapshot, snapshot_loaded
from tools.repo_twin.view import GraphView


def render_report(scan: ScanResult, storage_root: Path, *, output_format: str) -> str:
    findings = evaluate_findings(scan, storage_root)
    if output_format == "json":
        return json.dumps(_report_json(scan, storage_root, findings), indent=2, sort_keys=True)
    return _report_markdown(scan, storage_root, findings)


def _report_json(scan: ScanResult, storage_root: Path, findings: tuple[Finding, ...]) -> JsonObject:
    if not snapshot_loaded(storage_root):
        components: list[JsonObject] = []
    else:
        components = GraphView.from_snapshot(current_snapshot(storage_root)).components()
    return cast(
        JsonObject,
        {
            "components": components,
            "findings": [finding.to_json() for finding in findings],
        },
    )


def _report_markdown(scan: ScanResult, storage_root: Path, findings: tuple[Finding, ...]) -> str:
    lines = ["# Repo Twin Report", ""]
    if not snapshot_loaded(storage_root):
        lines.extend(["No synced repo twin snapshot exists.", ""])
    else:
        view = GraphView.from_snapshot(current_snapshot(storage_root))
        lines.extend(
            [
                "| Component | Status | Model authority | Implementations | Tests | Evidence |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for component in view.components():
            impl_values = component.get("implementation_roots")
            test_values = component.get("test_suites")
            impls = (
                ", ".join(str(item) for item in impl_values)
                if isinstance(impl_values, list)
                else ""
            )
            tests = (
                ", ".join(str(item) for item in test_values)
                if isinstance(test_values, list)
                else ""
            )
            lines.append(
                (
                    "| {component_id} | {status} | {spec_path} | {impls} | {tests} | {evidence} |"
                ).format(
                    component_id=component["component_id"],
                    status=component["status"],
                    spec_path=component["spec_path"],
                    impls=impls or "-",
                    tests=tests or "-",
                    evidence=component.get("newest_evidence_at") or "-",
                )
            )
        lines.append("")
    if findings:
        lines.extend(["## Findings", ""])
        lines.extend(
            [
                "| Severity | Finding | Subject | Detail |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in findings:
            lines.append(
                f"| {finding.severity} | {finding.finding_id} | {finding.subject} | "
                f"{finding.detail} |"
            )
        lines.append("")
    else:
        lines.extend(["No findings.", ""])
    return "\n".join(lines).rstrip() + "\n"
