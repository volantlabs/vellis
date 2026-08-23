from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator

try:
    from .model_layout import SYSTEM_EVOLUTION_PATH, SYSTEM_EVOLUTION_SCHEMA_PATH
    from .record_common import UniqueKeyLoader
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import (  # type: ignore[no-redef]
        SYSTEM_EVOLUTION_PATH,
        SYSTEM_EVOLUTION_SCHEMA_PATH,
    )
    from record_common import UniqueKeyLoader  # type: ignore[no-redef]


def load_record(path: Path = SYSTEM_EVOLUTION_PATH) -> dict[str, Any]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)  # noqa: S506
    if not isinstance(value, dict):
        raise ValueError(f"{path}: evolution record must be a YAML mapping")
    return cast(dict[str, Any], value)


def load_schema(path: Path = SYSTEM_EVOLUTION_SCHEMA_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: schema must be a JSON object")
    Draft202012Validator.check_schema(value)
    return cast(dict[str, Any], value)


def _json_path(parts: Any) -> str:
    return ".".join(str(part) for part in parts) or "record"


def schema_findings(record: dict[str, Any], schema_path: Path) -> list[str]:
    errors = sorted(
        Draft202012Validator(load_schema(schema_path)).iter_errors(record),
        key=lambda error: list(error.absolute_path),
    )
    return [f"{_json_path(error.absolute_path)}: {error.message}" for error in errors]


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


def _identifier_findings(
    findings_by_id: dict[str, dict[str, Any]],
    decisions_by_id: dict[str, dict[str, Any]],
    work_by_id: dict[str, dict[str, Any]],
    record: dict[str, Any],
) -> list[str]:
    result: list[str] = []
    groups = (
        ("finding", [entry["id"] for entry in record["findings"]]),
        ("decision", [entry["id"] for entry in record["decisions"]]),
        ("work item", [entry["id"] for entry in record["work_items"]]),
    )
    for label, identifiers in groups:
        result.extend(f"duplicate {label} ID: {value}" for value in _duplicates(identifiers))
    all_ids = [*findings_by_id, *decisions_by_id, *work_by_id]
    result.extend(
        f"ID {value} is reused across the evolution record" for value in _duplicates(all_ids)
    )
    return result


def _work_reference_findings(
    work_by_id: dict[str, dict[str, Any]],
    findings_by_id: dict[str, dict[str, Any]],
    decisions_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    result: list[str] = []
    for item in work_by_id.values():
        result.extend(_dependency_findings(item, work_by_id))
        result.extend(
            f"{item['id']} owns unknown finding {value}"
            for value in item["finding_ids"]
            if value not in findings_by_id
        )
        result.extend(
            f"{item['id']} owns unknown decision {value}"
            for value in item["decision_ids"]
            if value not in decisions_by_id
        )
    result.extend(_cycle_findings(work_by_id))
    return result


def _dependency_findings(item: dict[str, Any], work_by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for dependency in item["dependencies"]:
        if dependency not in work_by_id:
            result.append(f"{item['id']} depends on unknown work item {dependency}")
    return result


def _finding_owner_findings(
    finding: dict[str, Any], work_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    result: list[str] = []
    owner = finding["owner_work_item_id"]
    if owner not in work_by_id:
        result.append(f"finding {finding['id']} names unknown owner {owner}")
    elif finding["id"] not in work_by_id[owner]["finding_ids"]:
        result.append(f"finding {finding['id']} is not listed by owner {owner}")
    listed_by = [item["id"] for item in work_by_id.values() if finding["id"] in item["finding_ids"]]
    if listed_by != [owner]:
        result.append(f"finding {finding['id']} is listed by {listed_by}, expected [{owner!r}]")
    if finding["disposition"] == "resolved" and not finding["evidence_refs"]:
        result.append(f"resolved finding {finding['id']} has no evidence")
    if finding["disposition"] == "accepted" and not finding["evidence_refs"]:
        result.append(f"accepted finding {finding['id']} has no acceptance evidence")
    if finding["disposition"] == "out-of-scope" and not finding["evidence_refs"]:
        result.append(f"out-of-scope finding {finding['id']} has no disposition evidence")
    return result


def _decision_owner_findings(
    decision: dict[str, Any], work_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    result: list[str] = []
    owner = decision["owner_work_item_id"]
    if owner not in work_by_id:
        result.append(f"decision {decision['id']} names unknown owner {owner}")
    elif decision["id"] not in work_by_id[owner]["decision_ids"]:
        result.append(f"decision {decision['id']} is not listed by owner {owner}")
    listed_by = [
        item["id"] for item in work_by_id.values() if decision["id"] in item["decision_ids"]
    ]
    if listed_by != [owner]:
        result.append(f"decision {decision['id']} is listed by {listed_by}, expected [{owner!r}]")
    if decision["implementation_status"] == "conforming" and not decision["evidence_refs"]:
        result.append(f"conforming decision {decision['id']} has no evidence")
    return result


def _ownership_findings(
    findings_by_id: dict[str, dict[str, Any]],
    decisions_by_id: dict[str, dict[str, Any]],
    work_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    result: list[str] = []
    for finding in findings_by_id.values():
        result.extend(_finding_owner_findings(finding, work_by_id))
    for decision in decisions_by_id.values():
        result.extend(_decision_owner_findings(decision, work_by_id))
    return result


def _dependency_state_findings(
    item: dict[str, Any], work_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    if item["lifecycle"] not in {"ready", "active", "complete"}:
        return []
    incomplete = [
        value
        for value in item["dependencies"]
        if value in work_by_id and work_by_id[value]["lifecycle"] != "complete"
    ]
    if not incomplete:
        return []
    return [f"{item['lifecycle']} work item {item['id']} has incomplete dependencies {incomplete}"]


def _frontier_findings(record: dict[str, Any], work_by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []
    active = [item for item in work_by_id.values() if item["lifecycle"] == "active"]
    ready = [item for item in work_by_id.values() if item["lifecycle"] == "ready"]
    lifecycle = record["evolution"]["lifecycle"]
    if len(active) > 1:
        result.append("more than one work item is active")
    if active and lifecycle != "active":
        result.append("an active work item requires an active evolution")
    if lifecycle == "active" and len(active) != 1:
        result.append("an active evolution requires exactly one active work item")
    if lifecycle == "ready" and not ready:
        result.append("a ready evolution requires at least one ready work item")
    if ready and lifecycle != "ready":
        result.append("a ready work item requires a ready evolution")
    if lifecycle in {"discovery", "planning", "awaiting-approval"} and (active or ready):
        result.append(f"a {lifecycle} evolution cannot contain executable work")
    if lifecycle == "awaiting-approval" and record["evolution"]["approval"]["status"] != "pending":
        result.append("an awaiting-approval evolution requires a pending approval")
    return result


def _work_blocker_findings(item: dict[str, Any]) -> list[str]:
    result: list[str] = []
    if item["blocker"] is not None and item["lifecycle"] != "blocked":
        result.append(f"work item {item['id']} has a blocker but is not blocked")
    if item["lifecycle"] == "blocked" and item["blocker"] is None:
        result.append(f"blocked work item {item['id']} has no blocker")
    if item["lifecycle"] == "stale" and item["blocker"] is None:
        result.append(f"stale work item {item['id']} has no blocker")
    return result


def _blocker_findings(
    record: dict[str, Any],
    work_by_id: dict[str, dict[str, Any]],
    findings_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    result: list[str] = []
    lifecycle = record["evolution"]["lifecycle"]
    blocker = record["evolution"]["blocker"]
    approval = record["evolution"]["approval"]
    if approval["status"] == "accepted" and approval["checkpoint"] is None:
        result.append("accepted evolution approval has no attributable checkpoint")
    if blocker is not None and lifecycle not in {"blocked", "stale"}:
        result.append("an evolution blocker requires a blocked or stale lifecycle")
    if (
        lifecycle == "blocked"
        and blocker is None
        and not any(item["blocker"] is not None for item in work_by_id.values())
    ):
        result.append("blocked evolution has no blocker")
    labeled = [("evolution", blocker)]
    labeled.extend((f"work item {item['id']}", item["blocker"]) for item in work_by_id.values())
    for label, value in labeled:
        if value is None:
            continue
        result.extend(
            f"{label} blocker names unknown finding {finding_id}"
            for finding_id in value["finding_ids"]
            if finding_id not in findings_by_id
        )
    return result


def _completed_work_findings(
    item: dict[str, Any],
    findings_by_id: dict[str, dict[str, Any]],
    decisions_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    if item["lifecycle"] != "complete":
        return []
    result: list[str] = []
    if item["checkpoint"] is None:
        result.append(f"complete work item {item['id']} has no checkpoint")
    if not item["evidence_refs"]:
        result.append(f"complete work item {item['id']} has no evidence")
    if item["blocker"] is not None:
        result.append(f"complete work item {item['id']} retains a blocker")
    if item["implementation_status"] not in {"conforming", "not applicable"}:
        result.append(
            f"complete work item {item['id']} has implementation status "
            f"{item['implementation_status']}"
        )
    closed = {"resolved", "accepted", "out-of-scope"}
    open_findings = [
        value
        for value in item["finding_ids"]
        if value in findings_by_id and findings_by_id[value]["disposition"] not in closed
    ]
    if open_findings:
        result.append(f"complete work item {item['id']} has open findings {open_findings}")
    incomplete = [
        value
        for value in item["decision_ids"]
        if value in decisions_by_id
        and decisions_by_id[value]["implementation_status"] not in {"conforming", "not applicable"}
    ]
    if incomplete:
        result.append(f"complete work item {item['id']} has incomplete decisions {incomplete}")
    return result


def _acceptance_findings(item: dict[str, Any]) -> list[str]:
    result: list[str] = []
    identifiers = [entry["id"] for entry in item["acceptance"]]
    result.extend(
        f"duplicate acceptance ID in {item['id']}: {value}" for value in _duplicates(identifiers)
    )
    carried = set(item["evidence_refs"])
    claimed = {entry["evidence_ref"] for entry in item["acceptance"]}
    result.extend(
        f"acceptance {item['id']}.{entry['id']} names evidence the work item does not carry: "
        f"{entry['evidence_ref']}"
        for entry in item["acceptance"]
        if entry["evidence_ref"] not in carried
    )
    if item["lifecycle"] != "complete":
        return result
    result.extend(
        f"complete work item {item['id']} carries evidence no acceptance entry claims: {value}"
        for value in sorted(carried - claimed)
    )
    return result


def _closure_review_findings(record: dict[str, Any]) -> list[str]:
    """Closure reads the latest review per lens over the append-only log.

    Repeated lenses are legal: a lens that reported findings and later reported
    clean has been satisfied, and the record must be able to say so rather than
    forcing every pair to start from a record that cannot express what was
    already cleared.
    """
    required = set(record["scope"]["review_lenses"])
    closure_reviews = [review for review in record["reviews"] if review["scope"] == "closure"]
    latest = {review["lens"]: review for review in closure_reviews}
    result: list[str] = []
    undeclared = latest.keys() - required
    if undeclared:
        result.append(f"complete evolution has undeclared review lenses {sorted(undeclared)}")
    unresolved = sorted(lens for lens, review in latest.items() if review["status"] != "clean")
    if unresolved:
        result.append(f"complete evolution has unresolved reviews {unresolved}")
    clean = {lens: review for lens, review in latest.items() if review["status"] == "clean"}
    missing = required - clean.keys()
    if missing:
        result.append(f"complete evolution lacks clean required review lenses {sorted(missing)}")
    target = record["baselines"]["target"]
    target_implementation = None if target is None else target["implementation"]
    for lens in required & clean.keys():
        result.extend(_clean_review_findings(lens, clean[lens], target_implementation))
    return result


def _clean_review_findings(
    lens: str, review: dict[str, Any], target_implementation: str | None
) -> list[str]:
    result: list[str] = []
    if not review["evidence_refs"]:
        result.append(f"clean required review {lens!r} has no attributable evidence")
    if review["reviewer"] is None or review["checkpoint"] is None:
        result.append(f"clean required review {lens!r} lacks reviewer attribution")
    if review["checkpoint"] != target_implementation:
        result.append(f"clean required review {lens!r} is not bound to the target implementation")
    return result


def _complete_evolution_findings(
    record: dict[str, Any],
    findings_by_id: dict[str, dict[str, Any]],
    decisions_by_id: dict[str, dict[str, Any]],
    work_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    if record["evolution"]["lifecycle"] != "complete":
        return []
    closure = record["closure"]
    result = _complete_header_findings(record, work_by_id)
    result.extend(_complete_content_findings(closure, findings_by_id, decisions_by_id))
    result.extend(_closure_dimension_findings(closure))
    if not closure["evidence_refs"]:
        result.append("complete evolution has no closure evidence")
    result.extend(_closure_review_findings(record))
    return result


def _complete_header_findings(
    record: dict[str, Any], work_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    closure = record["closure"]
    result: list[str] = []
    if any(item["lifecycle"] != "complete" for item in work_by_id.values()):
        result.append("complete evolution has incomplete work items")
    if closure["checkpoint"] is None:
        result.append("complete evolution has no closure checkpoint")
    if record["evolution"]["checkpoint"] is None:
        result.append("complete evolution has no evolution checkpoint")
    elif record["evolution"]["checkpoint"] != closure["checkpoint"]:
        result.append("complete evolution and closure checkpoints must match")
    if record["evolution"]["approval"]["status"] not in {"accepted", "not-required"}:
        result.append("complete evolution has an unsatisfied approval roll-up")
    if record["evolution"]["blocker"] is not None:
        result.append("complete evolution retains a blocker")
    if record["baselines"]["target"] is None:
        result.append("complete evolution requires a target baseline")
    return result


def _complete_content_findings(
    closure: dict[str, Any],
    findings_by_id: dict[str, dict[str, Any]],
    decisions_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    result: list[str] = []
    closed = {"resolved", "accepted", "out-of-scope"}
    open_findings = [
        value["id"] for value in findings_by_id.values() if value["disposition"] not in closed
    ]
    if open_findings:
        result.append(f"complete evolution has open findings {open_findings}")
    incomplete = [
        value["id"]
        for value in decisions_by_id.values()
        if value["implementation_status"] not in {"conforming", "not applicable"}
    ]
    if incomplete:
        result.append(f"complete evolution has incomplete decisions {incomplete}")
    if closure["model_status"] not in {"accepted", "unchanged"}:
        result.append("complete evolution requires accepted or unchanged model status")
    return result


def _closure_dimension_findings(closure: dict[str, Any]) -> list[str]:
    return [
        f"complete evolution requires conforming or not-applicable {dimension}"
        for dimension in ("implementation_status",)
        if closure[dimension] not in {"conforming", "not applicable"}
    ]


def _review_state_findings(record: dict[str, Any], work_ids: set[str]) -> list[str]:
    result: list[str] = []
    for review in record["reviews"]:
        if review["scope"] != "closure" and review["scope"] not in work_ids:
            result.append(f"review {review['lens']!r} names unknown scope {review['scope']}")
        attributed = review["reviewer"] is not None and review["checkpoint"] is not None
        if review["status"] in {"findings", "clean"} and not attributed:
            result.append(f"review {review['lens']!r} lacks reviewer attribution")
        if review["status"] in {"findings", "clean"} and not review["evidence_refs"]:
            result.append(f"review {review['lens']!r} has no attributable evidence")
        if review["status"] == "pending" and (attributed or review["evidence_refs"]):
            result.append(f"pending review {review['lens']!r} retains completed-review state")
    return result


def invariant_findings(record: dict[str, Any]) -> list[str]:
    findings_by_id = {entry["id"]: entry for entry in record["findings"]}
    decisions_by_id = {entry["id"]: entry for entry in record["decisions"]}
    work_by_id = {entry["id"]: entry for entry in record["work_items"]}
    result = _identifier_findings(findings_by_id, decisions_by_id, work_by_id, record)
    result.extend(_work_reference_findings(work_by_id, findings_by_id, decisions_by_id))
    result.extend(_ownership_findings(findings_by_id, decisions_by_id, work_by_id))
    for item in work_by_id.values():
        result.extend(_dependency_state_findings(item, work_by_id))
        result.extend(_work_blocker_findings(item))
        result.extend(_acceptance_findings(item))
        result.extend(_completed_work_findings(item, findings_by_id, decisions_by_id))
    result.extend(_frontier_findings(record, work_by_id))
    result.extend(_blocker_findings(record, work_by_id, findings_by_id))
    result.extend(_complete_evolution_findings(record, findings_by_id, decisions_by_id, work_by_id))
    result.extend(_review_state_findings(record, set(work_by_id)))
    return result
