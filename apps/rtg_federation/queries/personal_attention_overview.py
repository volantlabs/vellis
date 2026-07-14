from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from apps.rtg_federation.canned_queries import (
    PERSONAL_ATTENTION_OVERVIEW,
    CannedQuery,
    graph_local_anchor_uuid,
)

FACT_REQUIREMENTS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "commitment_facts",
        "CommitmentFacts",
        "commitment",
        ("title", "domain", "status", "priority", "due", "made_to", "source", "confidence"),
    ),
    (
        "routine_facts",
        "RoutineFacts",
        "routine",
        ("title", "domain", "cadence", "status", "next_due", "blocker"),
    ),
    (
        "decision_facts",
        "DecisionFacts",
        "decision",
        ("title", "domain", "status", "decided_at", "rationale", "reversibility", "review_date"),
    ),
    (
        "evidence_facts",
        "EvidenceFacts",
        "evidence",
        ("title", "domain", "kind", "locator", "observed_at", "confidence"),
    ),
    (
        "relationship_context_facts",
        "RelationshipContextFacts",
        "relationship_context",
        ("person_name", "relationship", "domain", "last_contact", "preference", "open_loop"),
    ),
    (
        "goal_facts",
        "GoalFacts",
        "goal",
        ("title", "domain", "horizon", "status", "confidence", "success_signal", "review_date"),
    ),
    (
        "review_facts",
        "ReviewFacts",
        "review",
        ("title", "domain", "cadence", "period_start", "period_end", "summary"),
    ),
)

ATTENTION_STATUSES = {"active", "next", "waiting", "decided"}
CLOSED_STATUSES = {"done", "complete", "completed", "cancelled", "canceled", "closed"}
LOW_TRUST_CONFIDENCE = {"low", "medium", "unknown", "placeholder"}
EMPTY_MARKERS = {"", "none", "n/a", "na", "null", "no blocker"}
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True, slots=True)
class AttentionWindow:
    label: str
    start: date
    end: date


def summarize(query: dict[str, Any]) -> dict[str, Any]:
    result = query.get("result")
    if not isinstance(result, dict):
        return {"status": "query_unavailable"}
    rows = result.get("rows", result.get("returns"))
    if not isinstance(rows, list):
        return {"status": "query_rows_unavailable"}

    records = [_record_from_row(row) for row in rows if isinstance(row, dict)]
    records = [record for record in records if record is not None]
    counts_by_kind = _counts_by_kind(records)
    commitments = [record for record in records if record["kind"] == "commitment"]
    routines = [record for record in records if record["kind"] == "routine"]
    decisions = [record for record in records if record["kind"] == "decision"]
    evidence = [record for record in records if record["kind"] == "evidence"]
    relationships = [record for record in records if record["kind"] == "relationship_context"]
    goals = [record for record in records if record["kind"] == "goal"]
    attention_window = _attention_window(query)

    attention_items = sorted(
        [record for record in records if _needs_attention(record, attention_window)],
        key=_attention_sort_key,
    )
    evidence_gaps = sorted(
        [record for record in evidence if _is_low_trust(record.get("confidence"))],
        key=_title_sort_key,
    )
    high_priority_without_high_confidence = sorted(
        [
            record
            for record in commitments
            if _normal(record.get("priority")) == "high"
            and _normal(record.get("confidence")) != "high"
        ],
        key=_attention_sort_key,
    )

    return {
        "status": "summarized",
        "item_count": len(records),
        "counts_by_kind": counts_by_kind,
        "attention_scope": attention_window.label
        if attention_window is not None
        else "all_open_items",
        "attention_window": _public_attention_window(attention_window),
        "attention_item_count": len(attention_items),
        "attention_items": [_public_record(record) for record in attention_items],
        "commitment_count": len(commitments),
        "routine_count": len(routines),
        "decision_count": len(decisions),
        "goal_count": len(goals),
        "evidence_count": len(evidence),
        "strong_evidence_count": sum(
            1 for record in evidence if _normal(record.get("confidence")) == "high"
        ),
        "evidence_gap_count": len(evidence_gaps),
        "evidence_gaps": [_public_record(record) for record in evidence_gaps],
        "high_priority_commitments_without_high_confidence_count": len(
            high_priority_without_high_confidence
        ),
        "high_priority_commitments_without_high_confidence": [
            _public_record(record) for record in high_priority_without_high_confidence
        ],
        "relationship_open_loop_count": sum(
            1 for record in relationships if _has_text(record.get("open_loop"))
        ),
        "relationship_open_loops": [
            _public_record(record)
            for record in sorted(relationships, key=_title_sort_key)
            if _has_text(record.get("open_loop"))
        ],
    }


def citations_for_answer(
    graph_id: str,
    answer: dict[str, Any],
) -> tuple[dict[str, str | None], ...]:
    cited: dict[tuple[str, str], dict[str, str | None]] = {}
    for section in ("attention_items", "evidence_gaps"):
        items = answer.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            title = item.get("title")
            local_uuid = item.get("local_uuid")
            if (
                not isinstance(kind, str)
                or not isinstance(title, str)
                or not title
                or not isinstance(local_uuid, str)
            ):
                continue
            key = (kind, local_uuid)
            cited.setdefault(
                key,
                {
                    "graph_id": graph_id,
                    "local_uuid": local_uuid,
                    "label": title,
                    "kind": kind,
                },
            )
    return tuple(cited[key] for key in sorted(cited))


def _record_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    local_uuid = graph_local_anchor_uuid(row, "item")
    if local_uuid is None:
        return None
    properties = row.get("properties")
    if not isinstance(properties, dict):
        return None
    for requirement_name, _, kind, _ in FACT_REQUIREMENTS:
        facts = properties.get(requirement_name)
        if not isinstance(facts, dict):
            continue
        record = dict(facts)
        if kind == "evidence" and isinstance(record.get("kind"), str):
            record["evidence_kind"] = record["kind"]
        record["kind"] = kind
        record["local_uuid"] = local_uuid
        title = _title_for(record)
        if title:
            record["title"] = title
        return record
    return None


def _title_for(record: dict[str, Any]) -> str | None:
    title = record.get("title")
    if isinstance(title, str) and title:
        return title
    person_name = record.get("person_name")
    if isinstance(person_name, str) and person_name:
        return person_name
    return None


def _needs_attention(record: dict[str, Any], window: AttentionWindow | None) -> bool:
    kind = record["kind"]
    status = _normal(record.get("status"))
    if status in CLOSED_STATUSES:
        return False
    if kind == "commitment":
        return (status in ATTENTION_STATUSES or _normal(record.get("priority")) == "high") and (
            _within_attention_window(record, window, ("due",), include_missing=True)
        )
    if kind == "routine":
        return (status in ATTENTION_STATUSES or _has_text(record.get("blocker"))) and (
            _within_attention_window(record, window, ("next_due",), include_missing=True)
        )
    if kind == "decision":
        return (
            status in ATTENTION_STATUSES
            and _has_text(record.get("review_date"))
            and _within_attention_window(record, window, ("review_date",), include_missing=False)
        )
    if kind == "relationship_context":
        return _has_text(record.get("open_loop"))
    if kind == "goal":
        return (
            status in ATTENTION_STATUSES
            and _has_text(record.get("review_date"))
            and _within_attention_window(record, window, ("review_date",), include_missing=False)
        )
    return False


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "kind",
        "title",
        "local_uuid",
        "domain",
        "status",
        "priority",
        "due",
        "next_due",
        "review_date",
        "confidence",
        "blocker",
        "open_loop",
        "made_to",
        "evidence_kind",
        "observed_at",
    )
    return {key: record[key] for key in keys if key in record}


def _public_attention_window(window: AttentionWindow | None) -> dict[str, str] | None:
    if window is None:
        return None
    return {
        "label": window.label,
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
    }


def _counts_by_kind(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        kind = str(record["kind"])
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def _attention_sort_key(record: dict[str, Any]) -> tuple[int, str, str]:
    priority = _normal(record.get("priority"))
    due = str(
        record.get("due") or record.get("next_due") or record.get("review_date") or "9999-12-31"
    )
    return (PRIORITY_RANK.get(priority, 3), due, str(record.get("title") or ""))


def _title_sort_key(record: dict[str, Any]) -> tuple[str, str]:
    return (str(record.get("domain") or ""), str(record.get("title") or ""))


def _is_low_trust(value: Any) -> bool:
    confidence = _normal(value)
    return not confidence or confidence in LOW_TRUST_CONFIDENCE


def _has_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return _normal(value) not in EMPTY_MARKERS


def _normal(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _attention_window(query: dict[str, Any]) -> AttentionWindow | None:
    text = _request_text(query)
    if not text:
        return None
    normalized = text.lower()
    today = _request_today(query)
    if "today" in normalized:
        return AttentionWindow(label="today", start=today, end=today)
    if "this week" in normalized or "week" in normalized or "next 7 days" in normalized:
        return AttentionWindow(label="this_week", start=today, end=today + timedelta(days=7))
    return None


def _request_text(query: dict[str, Any]) -> str:
    request = query.get("request")
    if not isinstance(request, dict):
        return ""
    text = request.get("text")
    return text if isinstance(text, str) else ""


def _request_today(query: dict[str, Any]) -> date:
    request = query.get("request")
    if isinstance(request, dict):
        today = _parse_date(request.get("today"))
        if today is not None:
            return today
    return _today()


def _within_attention_window(
    record: dict[str, Any],
    window: AttentionWindow | None,
    fields: tuple[str, ...],
    *,
    include_missing: bool,
) -> bool:
    if window is None:
        return True
    dates = [_parse_date(record.get(field)) for field in fields if _has_text(record.get(field))]
    parsed_dates = [item for item in dates if item is not None]
    if not parsed_dates:
        return include_missing
    return any(item <= window.end for item in parsed_dates)


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _today() -> date:
    return date.today()


def _query_properties() -> list[list[object]]:
    properties: list[list[object]] = []
    for requirement_name, _, _, fields in FACT_REQUIREMENTS:
        for field in fields:
            properties.append([requirement_name, [field]])
    return properties


CANNED_QUERY = CannedQuery(
    name=PERSONAL_ATTENTION_OVERVIEW,
    description=(
        "Summarize personal operating graph commitments, routines, decisions, evidence, "
        "relationship contexts, goals, and reviews that need attention."
    ),
    query_spec={
        "anchor_buckets": [
            {
                "name": "item",
                "anchor_type_keys": [
                    "Commitment",
                    "Routine",
                    "Decision",
                    "Evidence",
                    "RelationshipContext",
                    "Goal",
                    "Review",
                ],
            }
        ],
        "data_requirements": [
            {
                "name": requirement_name,
                "anchor_bucket": "item",
                "data_type_key": data_type,
                "required": False,
            }
            for requirement_name, data_type, _, _ in FACT_REQUIREMENTS
        ],
        "return_spec": {
            "anchor_buckets": ["item"],
            "data_requirements": [item[0] for item in FACT_REQUIREMENTS],
            "properties": _query_properties(),
        },
    },
    query_options={"live_filter": "live"},
    response_options={"format": "full"},
    summarize=summarize,
    citations_for_answer=citations_for_answer,
)
