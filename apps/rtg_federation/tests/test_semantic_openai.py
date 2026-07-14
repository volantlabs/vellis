from __future__ import annotations

import json
from typing import Any

import pytest

from apps.rtg_federation.semantic_openai import (
    OpenAiResponsesSemanticDraftGenerator,
    OpenAiSemanticAdapterError,
    openai_semantic_generator_from_environment,
)
from components.rtg.evidence_bounded_synthesis import RtgEvidenceBoundedSynthesisRequest
from components.rtg.federated_synthesis import (
    RtgFederatedCitation,
    RtgFederatedGraphRead,
    RtgFederatedSynthesisRecord,
)


class RecordingTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def create_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(payload)
        return self.response


def test_openai_adapter_requests_strict_tool_free_structured_output() -> None:
    transport = RecordingTransport(
        _response(
            {
                "claims": [
                    {
                        "text": "Repo evidence and personal attention can be reviewed together.",
                        "kind": "comparison",
                        "citation_refs": [
                            {
                                "graph_id": "repo_twin",
                                "local_uuid": "11111111-1111-4111-8111-111111111111",
                            },
                            {
                                "graph_id": "personal_ops",
                                "local_uuid": "22222222-2222-4222-8222-222222222222",
                            },
                        ],
                        "uncertainty": None,
                    }
                ],
                "limitations": [],
            }
        )
    )
    generator = OpenAiResponsesSemanticDraftGenerator(transport, "gpt-5.6-luna")

    draft = generator.generate(_request())

    assert draft.claims[0].kind == "comparison"
    assert [reference.graph_id for reference in draft.claims[0].citation_refs] == [
        "repo_twin",
        "personal_ops",
    ]
    request = transport.requests[0]
    assert request["model"] == "gpt-5.6-luna"
    assert request["store"] is False
    assert "tools" not in request
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    envelope = json.loads(request["input"])
    assert envelope["intent_text"] == "Compare repo evidence with personal attention."
    assert {item["graph_id"] for item in envelope["source"]["citations"]} == {
        "repo_twin",
        "personal_ops",
    }


def test_openai_adapter_fails_closed_on_refusal() -> None:
    transport = RecordingTransport(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "Cannot comply."}],
                }
            ],
        }
    )

    with pytest.raises(OpenAiSemanticAdapterError, match="refused"):
        OpenAiResponsesSemanticDraftGenerator(transport, "gpt-5.6-luna").generate(_request())


def test_openai_adapter_requires_explicit_environment_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_OPENAI_API_KEY", raising=False)

    with pytest.raises(OpenAiSemanticAdapterError, match="TEST_OPENAI_API_KEY"):
        openai_semantic_generator_from_environment(
            model="gpt-5.6-luna",
            api_key_env="TEST_OPENAI_API_KEY",
        )


def _request() -> RtgEvidenceBoundedSynthesisRequest:
    repo_citation = RtgFederatedCitation(
        graph_id="repo_twin",
        local_uuid="11111111-1111-4111-8111-111111111111",
    )
    personal_citation = RtgFederatedCitation(
        graph_id="personal_ops",
        local_uuid="22222222-2222-4222-8222-222222222222",
    )
    source = RtgFederatedSynthesisRecord(
        status="complete",
        intent_text="Compare repo evidence with personal attention.",
        answer={"summary": "Executed two reads."},
        citations=(repo_citation, personal_citation),
        reads=(
            RtgFederatedGraphRead(
                graph_id="repo_twin",
                status="executed",
                query_name="repo_components_evidence_status",
                citations=(repo_citation,),
            ),
            RtgFederatedGraphRead(
                graph_id="personal_ops",
                status="executed",
                query_name="personal_attention_overview",
                citations=(personal_citation,),
            ),
        ),
        bridges=(),
        candidate_notices=(),
        limitations=(),
    )
    return RtgEvidenceBoundedSynthesisRequest(
        intent_text=source.intent_text,
        source=source,
    )


def _response(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(draft)}],
            }
        ],
    }
