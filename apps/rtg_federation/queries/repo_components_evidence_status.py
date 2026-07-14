from __future__ import annotations

from typing import Any

from apps.rtg_federation.canned_queries import (
    REPO_COMPONENTS_EVIDENCE_STATUS,
    CannedQuery,
    graph_local_anchor_uuid,
)


def summarize(query: dict[str, Any]) -> dict[str, Any]:
    result = query.get("result")
    if not isinstance(result, dict):
        return {"status": "query_unavailable"}
    rows = result.get("rows", result.get("returns"))
    if not isinstance(rows, list):
        return {"status": "query_rows_unavailable"}

    components: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        local_uuid = graph_local_anchor_uuid(row, "component")
        if local_uuid is None:
            continue
        properties = row.get("properties")
        if not isinstance(properties, dict):
            continue
        component_fact = properties.get("component_fact")
        if not isinstance(component_fact, dict):
            continue
        component_id = component_fact.get("component_id")
        if not isinstance(component_id, str) or not component_id:
            continue
        component = components.setdefault(
            component_id,
            {
                "component_id": component_id,
                "local_uuid": local_uuid,
                "status": component_fact.get("lifecycle_status", ""),
                "spec_path": component_fact.get("spec_path", ""),
                "evidence_count": 0,
                "newest_evidence_at": None,
            },
        )
        evidence = properties.get("evidence")
        if not isinstance(evidence, dict):
            continue
        component["evidence_count"] += 1
        produced_at = evidence.get("produced_at")
        if isinstance(produced_at, str) and (
            component["newest_evidence_at"] is None or produced_at > component["newest_evidence_at"]
        ):
            component["newest_evidence_at"] = produced_at

    ordered = sorted(components.values(), key=lambda item: str(item["component_id"]))
    missing = [
        component["component_id"] for component in ordered if component["evidence_count"] == 0
    ]
    return {
        "status": "summarized",
        "component_count": len(ordered),
        "missing_evidence_count": len(missing),
        "missing_evidence_component_ids": missing,
        "components": ordered,
    }


def citations_for_answer(
    graph_id: str,
    answer: dict[str, Any],
) -> tuple[dict[str, str | None], ...]:
    components = answer.get("components")
    if not isinstance(components, list):
        return ()
    citations: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            continue
        component_id = component.get("component_id")
        local_uuid = component.get("local_uuid")
        if (
            not isinstance(component_id, str)
            or not component_id
            or not isinstance(local_uuid, str)
            or local_uuid in seen
        ):
            continue
        seen.add(local_uuid)
        spec_path = component.get("spec_path")
        citations.append(
            {
                "graph_id": graph_id,
                "local_uuid": local_uuid,
                "label": spec_path if isinstance(spec_path, str) and spec_path else component_id,
                "kind": "component",
            }
        )
    return tuple(citations)


CANNED_QUERY = CannedQuery(
    name=REPO_COMPONENTS_EVIDENCE_STATUS,
    description=(
        "List repo-twin components and summarize which have no associated evidence records."
    ),
    query_spec={
        "anchor_buckets": [{"name": "component", "anchor_type_keys": ["twin.Component"]}],
        "data_requirements": [
            {
                "name": "component_fact",
                "anchor_bucket": "component",
                "data_type_key": "twin.ComponentFact",
            },
            {
                "name": "evidence",
                "anchor_bucket": "component",
                "data_type_key": "twin.EvidenceRecord",
                "required": False,
            },
        ],
        "return_spec": {
            "anchor_buckets": ["component"],
            "data_requirements": ["component_fact", "evidence"],
            "properties": [
                ["component_fact", ["component_id"]],
                ["component_fact", ["lifecycle_status"]],
                ["component_fact", ["spec_path"]],
                ["evidence", ["kind"]],
                ["evidence", ["passed"]],
                ["evidence", ["produced_at"]],
                ["evidence", ["summary"]],
            ],
        },
    },
    query_options={"live_filter": "live"},
    response_options={"format": "full"},
    summarize=summarize,
    citations_for_answer=citations_for_answer,
)
