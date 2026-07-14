from __future__ import annotations

from dataclasses import replace

import pytest

from components.rtg.evidence_bounded_synthesis import (
    EvidenceBoundedRtgSynthesizer,
    RtgEvidenceBoundedSynthesisInvalid,
    RtgEvidenceBoundedSynthesisRequest,
    RtgEvidenceCitationRef,
    RtgSemanticClaimDraft,
    RtgSemanticSynthesisDraft,
)
from components.rtg.evidence_bounded_synthesis.reference import create_reference_component
from components.rtg.federated_synthesis import (
    RtgFederatedBridgeContext,
    RtgFederatedCitation,
    RtgFederatedGraphRead,
    RtgFederatedSynthesisRecord,
)

MODEL_EVIDENCE = {
    "SemanticDraftGeneratorContractVerification": (
        "test_reference_component_produces_only_source_bound_summary_claims",
        "test_generator_receives_a_copy_and_component_exposes_no_write_operations",
    ),
    "SynthesizeEvidenceBoundedClaimsContractVerification": (
        "test_accepts_cross_graph_claim_with_source_bound_citations",
        "test_rejects_claims_that_escape_evidence_bounds",
        "test_propagates_source_and_generator_limitations",
        "test_does_not_invoke_generator_without_graph_qualified_evidence",
        "test_requires_the_source_and_semantic_intents_to_match",
        "test_open_requires_a_semantic_draft_generator",
    ),
    "RtgEvidenceBoundedSynthesizerBoundaryVerification": (
        "test_accepts_cross_graph_claim_with_source_bound_citations",
        "test_rejects_claims_that_escape_evidence_bounds",
        "test_does_not_invoke_generator_without_graph_qualified_evidence",
        "test_generator_receives_a_copy_and_component_exposes_no_write_operations",
        "test_reference_component_produces_only_source_bound_summary_claims",
    ),
    "OpenRtgEvidenceBoundedSynthesizerContractVerification": (
        "test_open_requires_a_semantic_draft_generator",
    ),
}

INTENT = "Compare repo evidence with personal operating decisions."
REPO_UUID = "11111111-1111-4111-8111-111111111111"
PERSONAL_UUID = "22222222-2222-4222-8222-222222222222"
UNKNOWN_UUID = "33333333-3333-4333-8333-333333333333"


class StaticGenerator:
    def __init__(self, draft: RtgSemanticSynthesisDraft) -> None:
        self.draft = draft
        self.call_count = 0

    def generate(
        self,
        request: RtgEvidenceBoundedSynthesisRequest,
    ) -> RtgSemanticSynthesisDraft:
        _ = request
        self.call_count += 1
        return self.draft


def test_open_requires_a_semantic_draft_generator() -> None:
    with pytest.raises(RtgEvidenceBoundedSynthesisInvalid, match="must provide generate"):
        EvidenceBoundedRtgSynthesizer.open(object())  # type: ignore[arg-type]


def test_accepts_cross_graph_claim_with_source_bound_citations() -> None:
    generator = StaticGenerator(
        RtgSemanticSynthesisDraft(
            claims=(
                RtgSemanticClaimDraft(
                    text=(
                        "The tested federation boundary and the personal hardening decision "
                        "support treating the life graph as a substrate exercise."
                    ),
                    kind="comparison",
                    citation_refs=(
                        RtgEvidenceCitationRef("repo_twin", REPO_UUID),
                        RtgEvidenceCitationRef("personal_ops", PERSONAL_UUID),
                    ),
                ),
            )
        )
    )
    synthesizer = EvidenceBoundedRtgSynthesizer.open(generator)

    result = synthesizer.synthesize(_request())

    assert result.status == "complete"
    assert result.source_status == "complete"
    assert result.entailment_status == "not_verified"
    assert len(result.claims) == 1
    assert {citation.graph_id for citation in result.claims[0].citations} == {
        "repo_twin",
        "personal_ops",
    }
    assert result.citations == result.claims[0].citations
    assert result.limitations == ()


@pytest.mark.parametrize(
    ("claim", "message"),
    [
        (
            RtgSemanticClaimDraft(
                text="Unknown evidence.",
                kind="summary",
                citation_refs=(RtgEvidenceCitationRef("repo_twin", UNKNOWN_UUID),),
            ),
            "absent from source evidence",
        ),
        (
            RtgSemanticClaimDraft(
                text="No evidence.",
                kind="summary",
                citation_refs=(),
            ),
            "every claim must cite",
        ),
        (
            RtgSemanticClaimDraft(
                text="Not actually cross graph.",
                kind="comparison",
                citation_refs=(RtgEvidenceCitationRef("repo_twin", REPO_UUID),),
            ),
            "at least two graph namespaces",
        ),
        (
            RtgSemanticClaimDraft(
                text="An undisclosed inference.",
                kind="inference",
                citation_refs=(RtgEvidenceCitationRef("repo_twin", REPO_UUID),),
            ),
            "must disclose uncertainty",
        ),
    ],
)
def test_rejects_claims_that_escape_evidence_bounds(
    claim: RtgSemanticClaimDraft,
    message: str,
) -> None:
    synthesizer = EvidenceBoundedRtgSynthesizer.open(
        StaticGenerator(RtgSemanticSynthesisDraft(claims=(claim,)))
    )

    with pytest.raises(RtgEvidenceBoundedSynthesisInvalid, match=message):
        synthesizer.synthesize(_request())


def test_propagates_source_and_generator_limitations() -> None:
    source = replace(_source(), status="partial", limitations=("Gothic read was unsupported.",))
    generator = StaticGenerator(
        RtgSemanticSynthesisDraft(
            claims=(
                RtgSemanticClaimDraft(
                    text="Repo evidence is available for review.",
                    kind="summary",
                    citation_refs=(RtgEvidenceCitationRef("repo_twin", REPO_UUID),),
                ),
            ),
            limitations=("The generator did not compare every graph.",),
        )
    )

    result = EvidenceBoundedRtgSynthesizer.open(generator).synthesize(
        RtgEvidenceBoundedSynthesisRequest(intent_text=INTENT, source=source)
    )

    assert result.status == "partial"
    assert result.limitations == (
        "Gothic read was unsupported.",
        "The generator did not compare every graph.",
    )


def test_does_not_invoke_generator_without_graph_qualified_evidence() -> None:
    generator = StaticGenerator(RtgSemanticSynthesisDraft(claims=()))
    source = replace(_source(), citations=())

    result = EvidenceBoundedRtgSynthesizer.open(generator).synthesize(
        RtgEvidenceBoundedSynthesisRequest(intent_text=INTENT, source=source)
    )

    assert result.status == "no_supported_claims"
    assert generator.call_count == 0
    assert result.claims == ()
    assert result.limitations == (
        "deterministic source has no graph-qualified citations",
    )


def test_requires_the_source_and_semantic_intents_to_match() -> None:
    synthesizer = EvidenceBoundedRtgSynthesizer.open(
        StaticGenerator(RtgSemanticSynthesisDraft(claims=()))
    )

    with pytest.raises(RtgEvidenceBoundedSynthesisInvalid, match="intent_text must match"):
        synthesizer.synthesize(
            RtgEvidenceBoundedSynthesisRequest(
                intent_text="A different question.",
                source=_source(),
            )
        )


def test_generator_receives_a_copy_and_component_exposes_no_write_operations() -> None:
    source = _source()

    class MutatingGenerator:
        def generate(
            self,
            request: RtgEvidenceBoundedSynthesisRequest,
        ) -> RtgSemanticSynthesisDraft:
            request.source.answer["summary"] = "mutated"
            return RtgSemanticSynthesisDraft(
                claims=(
                    RtgSemanticClaimDraft(
                        text="Repo evidence is available.",
                        kind="summary",
                        citation_refs=(RtgEvidenceCitationRef("repo_twin", REPO_UUID),),
                    ),
                )
            )

    synthesizer = EvidenceBoundedRtgSynthesizer.open(MutatingGenerator())

    result = synthesizer.synthesize(
        RtgEvidenceBoundedSynthesisRequest(intent_text=INTENT, source=source)
    )

    assert result.status == "complete"
    assert source.answer["summary"] == "deterministic source"
    for forbidden_name in (
        "execute_query",
        "resolve_citation",
        "traverse_bridge",
        "put_bridge",
        "write",
        "run_mcp_server",
    ):
        assert not hasattr(synthesizer, forbidden_name)


def test_reference_component_produces_only_source_bound_summary_claims() -> None:
    result = create_reference_component().synthesize(_request())

    assert result.status == "complete"
    assert len(result.claims) == 2
    assert {claim.kind for claim in result.claims} == {"summary"}
    assert all(len(claim.citations) == 1 for claim in result.claims)


def _request() -> RtgEvidenceBoundedSynthesisRequest:
    return RtgEvidenceBoundedSynthesisRequest(intent_text=INTENT, source=_source())


def _source() -> RtgFederatedSynthesisRecord:
    repo_citation = RtgFederatedCitation(
        graph_id="repo_twin",
        local_uuid=REPO_UUID,
        label="Bridge traversal component",
        kind="component",
    )
    personal_citation = RtgFederatedCitation(
        graph_id="personal_ops",
        local_uuid=PERSONAL_UUID,
        label="Life graph hardening decision",
        kind="decision",
    )
    return RtgFederatedSynthesisRecord(
        status="complete",
        intent_text=INTENT,
        answer={"summary": "deterministic source"},
        citations=(repo_citation, personal_citation),
        reads=(
            RtgFederatedGraphRead(
                graph_id="repo_twin",
                status="executed",
                query_name="repo_components_evidence_status",
                summary={"component_count": 20},
                citations=(repo_citation,),
            ),
            RtgFederatedGraphRead(
                graph_id="personal_ops",
                status="executed",
                query_name="personal_attention_overview",
                summary={"decision_count": 5},
                citations=(personal_citation,),
            ),
        ),
        bridges=(
            RtgFederatedBridgeContext(
                bridge_id="bridge_abcdef1234567890abcd",
                bridge_type="related_context",
                source_graph_id="repo_twin",
                source_local_id=REPO_UUID,
                target_graph_id="personal_ops",
                target_local_id=PERSONAL_UUID,
                confidence=0.9,
            ),
        ),
        candidate_notices=(),
        limitations=(),
    )
