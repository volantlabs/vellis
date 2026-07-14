from __future__ import annotations

from typing import Any

from apps.rtg_federation.canned_queries import CannedQuery, graph_local_anchor_uuid

QUERY_NAME = "gothic_source_index"

FACT_REQUIREMENTS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "work_facts",
        "WorkFacts",
        "work",
        (
            "title",
            "creator",
            "publication_year",
            "public_domain_basis",
            "source_language",
            "notes",
            "verification_status",
        ),
    ),
    (
        "source_facts",
        "SourceFacts",
        "source",
        (
            "label",
            "edition",
            "provider",
            "url",
            "license_status",
            "retrieved_at",
            "notes",
            "verification_status",
        ),
    ),
    (
        "passage_facts",
        "PassageFacts",
        "passage",
        ("label", "source_marker", "summary", "quote_policy", "verification_status"),
    ),
    (
        "reading_trail_facts",
        "ReadingTrailFacts",
        "reading_trail",
        ("label", "summary", "curation_status"),
    ),
)

VERIFIED_STATUSES = {"approved", "complete", "confirmed", "verified"}
VERIFICATION_KINDS = {"work", "source", "passage"}
SECTION_BY_KIND = {
    "work": "works",
    "source": "sources",
    "passage": "passages",
    "reading_trail": "reading_trails",
}


def summarize(query: dict[str, Any]) -> dict[str, Any]:
    result = query.get("result")
    if not isinstance(result, dict):
        return {"status": "query_unavailable"}
    rows = result.get("rows", result.get("returns"))
    if not isinstance(rows, list):
        return {"status": "query_rows_unavailable"}

    records = [_record_from_row(row) for row in rows if isinstance(row, dict)]
    ordered = sorted(
        (record for record in records if record is not None),
        key=lambda record: (str(record["kind"]), str(record["title"])),
    )
    sections = {
        section: [_public_record(record) for record in ordered if record["kind"] == kind]
        for kind, section in SECTION_BY_KIND.items()
    }
    verification_gaps = [
        _public_record(record)
        for record in ordered
        if record["kind"] in VERIFICATION_KINDS
        and _normal(record.get("verification_status")) not in VERIFIED_STATUSES
    ]

    return {
        "status": "summarized",
        "item_count": len(ordered),
        "counts_by_kind": {
            kind: sum(1 for record in ordered if record["kind"] == kind)
            for kind in SECTION_BY_KIND
        },
        **sections,
        "verification_gap_count": len(verification_gaps),
        "verification_gaps": verification_gaps,
    }


def citations_for_answer(
    graph_id: str,
    answer: dict[str, Any],
) -> tuple[dict[str, str | None], ...]:
    citations: list[dict[str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for kind, section in SECTION_BY_KIND.items():
        items = answer.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            local_uuid = item.get("local_uuid")
            if (
                not isinstance(title, str)
                or not title
                or not isinstance(local_uuid, str)
            ):
                continue
            key = (kind, local_uuid)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "graph_id": graph_id,
                    "local_uuid": local_uuid,
                    "label": title,
                    "kind": kind,
                }
            )
    return tuple(citations)


def _record_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    local_uuid = graph_local_anchor_uuid(row, "archive_item")
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
        title = record.get("title") or record.get("label")
        if not isinstance(title, str) or not title:
            return None
        record["kind"] = kind
        record["title"] = title
        record["local_uuid"] = local_uuid
        return record
    return None


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "kind",
        "title",
        "local_uuid",
        "creator",
        "publication_year",
        "public_domain_basis",
        "source_language",
        "edition",
        "provider",
        "url",
        "license_status",
        "retrieved_at",
        "source_marker",
        "summary",
        "quote_policy",
        "curation_status",
        "verification_status",
    )
    return {field: record[field] for field in fields if field in record}


def _normal(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _query_properties() -> list[list[object]]:
    return [
        [requirement_name, [field]]
        for requirement_name, _, _, fields in FACT_REQUIREMENTS
        for field in fields
    ]


CANNED_QUERY = CannedQuery(
    name=QUERY_NAME,
    description=(
        "Index Gothic archive works, sources, passages, and reading trails while surfacing "
        "source-verification gaps."
    ),
    query_spec={
        "anchor_buckets": [
            {
                "name": "archive_item",
                "anchor_type_keys": ["Work", "Source", "Passage", "ReadingTrail"],
            }
        ],
        "data_requirements": [
            {
                "name": requirement_name,
                "anchor_bucket": "archive_item",
                "data_type_key": data_type,
                "required": False,
            }
            for requirement_name, data_type, _, _ in FACT_REQUIREMENTS
        ],
        "return_spec": {
            "anchor_buckets": ["archive_item"],
            "data_requirements": [item[0] for item in FACT_REQUIREMENTS],
            "properties": _query_properties(),
        },
    },
    query_options={"live_filter": "live"},
    response_options={"format": "full"},
    summarize=summarize,
    citations_for_answer=citations_for_answer,
)
