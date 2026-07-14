from __future__ import annotations

from collections import Counter
from typing import Any

from apps.rtg_federation.canned_queries import CannedQuery, graph_local_anchor_uuid

QUERY_NAME = "experience_publication_readiness"
PASS_OUTCOMES = {"pass"}


def summarize(query: dict[str, Any]) -> dict[str, Any]:
    result = query.get("result")
    if not isinstance(result, dict):
        return {"status": "query_unavailable"}
    rows = result.get("rows", result.get("returns"))
    if not isinstance(rows, list):
        return {"status": "query_rows_unavailable"}

    checks = [_check_from_row(row) for row in rows if isinstance(row, dict)]
    ordered = sorted(
        (check for check in checks if check is not None),
        key=lambda check: (int(check["sequence_order"]), str(check["label"])),
    )
    outcome_counts = Counter(str(check["outcome"]) for check in ordered)
    open_checks = [check for check in ordered if check["outcome"] not in PASS_OUTCOMES]
    checked_at_values = [
        str(check["checked_at"]) for check in ordered if check.get("checked_at")
    ]
    experience_titles = sorted(
        {str(check["experience_title"]) for check in ordered if check.get("experience_title")}
    )
    return {
        "status": "summarized",
        "publication_status": "ready" if not open_checks else "review_required",
        "experience_titles": experience_titles,
        "check_count": len(ordered),
        "passed_check_count": len(ordered) - len(open_checks),
        "open_check_count": len(open_checks),
        "counts_by_outcome": dict(sorted(outcome_counts.items())),
        "latest_checked_at": max(checked_at_values, default=None),
        "checks": ordered,
        "open_checks": open_checks,
        "assurance_scope": "reviewable product-planning evidence, not legal certification",
    }


def citations_for_answer(
    graph_id: str,
    answer: dict[str, Any],
) -> tuple[dict[str, str | None], ...]:
    checks = answer.get("checks")
    if not isinstance(checks, list):
        return ()
    citations: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            continue
        local_uuid = check.get("local_uuid")
        label = check.get("label")
        if (
            not isinstance(local_uuid, str)
            or local_uuid in seen
            or not isinstance(label, str)
            or not label
        ):
            continue
        seen.add(local_uuid)
        citations.append(
            {
                "graph_id": graph_id,
                "local_uuid": local_uuid,
                "label": label,
                "kind": "publication_check",
            }
        )
    return tuple(citations)


def _check_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    local_uuid = graph_local_anchor_uuid(row, "check")
    properties = row.get("properties")
    if local_uuid is None or not isinstance(properties, dict):
        return None
    experience = properties.get("experience_facts")
    criterion = properties.get("criterion_facts")
    check = properties.get("check_facts")
    if not all(isinstance(value, dict) for value in (experience, criterion, check)):
        return None
    assert isinstance(experience, dict)
    assert isinstance(criterion, dict)
    assert isinstance(check, dict)
    label = criterion.get("label")
    outcome = check.get("outcome")
    sequence_order = criterion.get("sequence_order")
    if (
        not isinstance(label, str)
        or not label
        or not isinstance(outcome, str)
        or not outcome
        or not isinstance(sequence_order, int)
    ):
        return None
    return {
        "local_uuid": local_uuid,
        "experience_title": experience.get("title", ""),
        "sequence_order": sequence_order,
        "label": label,
        "category": criterion.get("category", ""),
        "checked_at": check.get("checked_at"),
        "outcome": outcome,
        "reviewer": check.get("reviewer", ""),
        "notes": check.get("notes", ""),
    }


CANNED_QUERY = CannedQuery(
    name=QUERY_NAME,
    description=(
        "Summarize ordered Experience Studio publication checks and surface unresolved review "
        "gates."
    ),
    query_spec={
        "anchor_buckets": [
            {"name": "check", "anchor_type_keys": ["PublicationCheck"]},
            {"name": "experience", "anchor_type_keys": ["Experience"]},
            {"name": "criterion", "anchor_type_keys": ["PublicationCriterion"]},
        ],
        "link_requirements": [
            {
                "name": "for_experience",
                "source_bucket": "check",
                "target_bucket": "experience",
                "link_type_keys": ["check_for"],
            },
            {
                "name": "criterion_checked",
                "source_bucket": "check",
                "target_bucket": "criterion",
                "link_type_keys": ["checks_criterion"],
            },
        ],
        "data_requirements": [
            {
                "name": "experience_facts",
                "anchor_bucket": "experience",
                "data_type_key": "ExperienceFacts",
            },
            {
                "name": "check_facts",
                "anchor_bucket": "check",
                "data_type_key": "PublicationCheckFacts",
            },
            {
                "name": "criterion_facts",
                "anchor_bucket": "criterion",
                "data_type_key": "PublicationCriterionFacts",
            },
        ],
        "return_spec": {
            "anchor_buckets": ["check", "experience", "criterion"],
            "link_requirements": ["for_experience", "criterion_checked"],
            "data_requirements": ["experience_facts", "check_facts", "criterion_facts"],
            "properties": [
                ["experience_facts", ["title"]],
                ["criterion_facts", ["sequence_order"]],
                ["criterion_facts", ["label"]],
                ["criterion_facts", ["category"]],
                ["check_facts", ["checked_at"]],
                ["check_facts", ["outcome"]],
                ["check_facts", ["reviewer"]],
                ["check_facts", ["notes"]],
            ],
        },
    },
    query_options={
        "live_filter": "live",
        "order_by": [
            {
                "data_requirement": "criterion_facts",
                "path": ["sequence_order"],
                "direction": "ascending",
            }
        ],
    },
    response_options={"format": "full"},
    summarize=summarize,
    citations_for_answer=citations_for_answer,
)
