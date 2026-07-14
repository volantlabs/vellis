from __future__ import annotations

from typing import Any

from apps.rtg_federation.queries.experience_publication_readiness import (
    CANNED_QUERY,
    citations_for_answer,
    summarize,
)

CHECK_ONE = "11111111-1111-4111-8111-111111111111"
CHECK_TWO = "22222222-2222-4222-8222-222222222222"


def test_publication_readiness_summarizes_ordered_checks_and_open_gates() -> None:
    answer = summarize(
        {
            "result": {
                "rows": [
                    _row(
                        local_uuid=CHECK_TWO,
                        sequence_order=2,
                        label="Human review is complete",
                        outcome="pending_human_review",
                        reviewer="unassigned",
                    ),
                    _row(
                        local_uuid=CHECK_ONE,
                        sequence_order=1,
                        label="Static snapshot is explicit",
                        outcome="pass",
                        reviewer="prototype verification",
                    ),
                    {"anchors": {}, "properties": {}},
                ]
            }
        }
    )

    assert answer["status"] == "summarized"
    assert answer["publication_status"] == "review_required"
    assert answer["experience_titles"] == ["Ocean Signal Atlas"]
    assert answer["check_count"] == 2
    assert answer["passed_check_count"] == 1
    assert answer["open_check_count"] == 1
    assert answer["counts_by_outcome"] == {"pass": 1, "pending_human_review": 1}
    assert [check["local_uuid"] for check in answer["checks"]] == [CHECK_ONE, CHECK_TWO]
    assert [check["local_uuid"] for check in answer["open_checks"]] == [CHECK_TWO]
    assert answer["assurance_scope"] == (
        "reviewable product-planning evidence, not legal certification"
    )


def test_publication_readiness_citations_are_graph_qualified_check_anchors() -> None:
    answer = summarize(
        {
            "result": {
                "rows": [
                    _row(
                        local_uuid=CHECK_ONE,
                        sequence_order=1,
                        label="Static snapshot is explicit",
                        outcome="pass",
                        reviewer="prototype verification",
                    )
                ]
            }
        }
    )

    assert citations_for_answer("experience_studio", answer) == (
        {
            "graph_id": "experience_studio",
            "local_uuid": CHECK_ONE,
            "label": "Static snapshot is explicit",
            "kind": "publication_check",
        },
    )


def test_publication_readiness_query_returns_the_citation_projection_bucket() -> None:
    assert CANNED_QUERY.name == "experience_publication_readiness"
    assert CANNED_QUERY.query_spec["return_spec"]["anchor_buckets"] == [
        "check",
        "experience",
        "criterion",
    ]
    assert CANNED_QUERY.query_options == {
        "live_filter": "live",
        "order_by": [
            {
                "data_requirement": "criterion_facts",
                "path": ["sequence_order"],
                "direction": "ascending",
            }
        ],
    }


def _row(
    *,
    local_uuid: str,
    sequence_order: int,
    label: str,
    outcome: str,
    reviewer: str,
) -> dict[str, Any]:
    return {
        "anchors": {
            "check": local_uuid,
            "experience": "33333333-3333-4333-8333-333333333333",
            "criterion": "44444444-4444-4444-8444-444444444444",
        },
        "properties": {
            "experience_facts": {"title": "Ocean Signal Atlas"},
            "criterion_facts": {
                "sequence_order": sequence_order,
                "label": label,
                "category": "human_review",
            },
            "check_facts": {
                "checked_at": "2026-07-10T00:00:00Z",
                "outcome": outcome,
                "reviewer": reviewer,
                "notes": "Fixture note.",
            },
        },
    }
