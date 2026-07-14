from __future__ import annotations

import copy

import pytest

from components.rtg.federated_synthesis import (
    RtgFederatedBridgeContext,
    RtgFederatedCandidateNotice,
    RtgFederatedCitation,
    RtgFederatedGraphRead,
    RtgFederatedSynthesisInvalid,
    RtgFederatedSynthesisRequest,
)
from components.rtg.federated_synthesis.reference import create_reference_component

MODEL_EVIDENCE = {
    "SynthesizeFederatedContextContractVerification": (
        "test_synthesizes_complete_record_with_graph_qualified_citations",
        "test_synthesizes_partial_record_with_candidate_and_unsupported_limitations",
        "test_synthesizes_no_supported_reads_without_inventing_facts",
        "test_validates_citation_and_read_shapes",
        "test_deduplicates_canonical_citation_identity_without_using_presentation_kind",
        "test_rejects_non_finite_bridge_and_summary_values",
        "test_rejects_invalid_bridge_and_candidate_context",
        "test_synthesis_returns_isolated_records_without_input_mutation",
    ),
    "RtgFederatedSynthesizerBoundaryVerification": (
        "test_synthesizes_complete_record_with_graph_qualified_citations",
        "test_synthesizes_partial_record_with_candidate_and_unsupported_limitations",
        "test_synthesizes_no_supported_reads_without_inventing_facts",
        "test_deduplicates_canonical_citation_identity_without_using_presentation_kind",
        "test_synthesis_returns_isolated_records_without_input_mutation",
        "test_synthesizer_does_not_expose_graph_or_bridge_mutation_operations",
    ),
}


def citation(
    local_uuid: str = "11111111-1111-4111-8111-111111111111",
) -> RtgFederatedCitation:
    return RtgFederatedCitation(
        graph_id="repo_twin",
        local_uuid=local_uuid,
        label="Graph Registry",
        kind="component",
    )


def test_synthesizes_complete_record_with_graph_qualified_citations() -> None:
    synthesizer = create_reference_component()
    repeated = citation()
    request = RtgFederatedSynthesisRequest(
        intent_text="Compare component evidence with personal decisions.",
        reads=(
            RtgFederatedGraphRead(
                graph_id="repo_twin",
                status="executed",
                query_name="repo_components_evidence_status",
                summary={"component_count": 2, "missing_evidence_count": 0},
                citations=(repeated, repeated),
            ),
        ),
        bridges=(
            RtgFederatedBridgeContext(
                bridge_id="bridge_deadbeef0000000000",
                bridge_type="related_context",
                source_graph_id="repo_twin",
                source_local_id="11111111-1111-4111-8111-111111111111",
                target_graph_id="personal_ops",
                target_local_id="22222222-2222-4222-8222-222222222222",
                confidence=0.66,
            ),
        ),
    )

    record = synthesizer.synthesize(request)

    assert record.status == "complete"
    assert record.answer["executed_graph_count"] == 1
    assert record.answer["bridge_count"] == 1
    assert len(record.citations) == 1
    assert record.citations[0].graph_id == "repo_twin"
    assert record.citations[0].local_uuid == "11111111-1111-4111-8111-111111111111"
    assert record.limitations == ()


def test_synthesizes_partial_record_with_candidate_and_unsupported_limitations() -> None:
    synthesizer = create_reference_component()
    request = RtgFederatedSynthesisRequest(
        intent_text="Compare component evidence with personal decisions.",
        reads=(
            RtgFederatedGraphRead(
                graph_id="repo_twin",
                status="executed",
                query_name="repo_components_evidence_status",
                summary={"component_count": 2},
                citations=(citation(),),
            ),
            RtgFederatedGraphRead(
                graph_id="personal_ops",
                status="unsupported",
                query_name=None,
                notes=("no supported federated canned query for this graph",),
            ),
        ),
        candidate_notices=(
            RtgFederatedCandidateNotice(
                candidate_id="candidate_deadbeef0000000000",
                status="candidate_only",
                traversal_permission=False,
                reason="candidate requires review",
            ),
        ),
    )

    record = synthesizer.synthesize(request)

    assert record.status == "partial"
    assert record.answer["planned_graph_count"] == 2
    assert record.answer["candidate_notice_count"] == 1
    assert record.limitations == (
        (
            "graph personal_ops read was unsupported: "
            "no supported federated canned query for this graph"
        ),
        "candidate candidate_deadbeef0000000000 not used for traversal: candidate requires review",
    )


def test_synthesizes_no_supported_reads_without_inventing_facts() -> None:
    synthesizer = create_reference_component()
    request = RtgFederatedSynthesisRequest(
        intent_text="Read a graph with no configured query.",
        reads=(
            RtgFederatedGraphRead(
                graph_id="personal_ops",
                status="unsupported",
                query_name=None,
                notes=("no supported federated canned query for this graph",),
            ),
        ),
    )

    record = synthesizer.synthesize(request)

    assert record.status == "no_supported_reads"
    assert record.citations == ()
    assert (
        record.answer["summary"] == "No graph-local reads were executed for this federated request."
    )


def test_validates_citation_and_read_shapes() -> None:
    synthesizer = create_reference_component()

    try:
        synthesizer.synthesize(
            RtgFederatedSynthesisRequest(
                intent_text="Bad citation",
                reads=(
                    RtgFederatedGraphRead(
                        graph_id="repo_twin",
                        status="executed",
                        query_name="repo_components_evidence_status",
                        citations=(
                            RtgFederatedCitation(
                                graph_id="repo_twin",
                                local_uuid="component.rtg.graph_registry",
                            ),
                        ),
                    ),
                ),
            )
        )
    except RtgFederatedSynthesisInvalid:
        pass
    else:
        raise AssertionError("non-UUID citation identity should fail")

    with pytest.raises(RtgFederatedSynthesisInvalid, match="read.graph_id namespace"):
        synthesizer.synthesize(
            RtgFederatedSynthesisRequest(
                intent_text="Cross-namespace citation",
                reads=(
                    RtgFederatedGraphRead(
                        graph_id="repo_twin",
                        status="executed",
                        query_name="repo_components_evidence_status",
                        citations=(
                            RtgFederatedCitation(
                                graph_id="personal_ops",
                                local_uuid="11111111-1111-4111-8111-111111111111",
                            ),
                        ),
                    ),
                ),
            )
        )


def test_deduplicates_canonical_citation_identity_without_using_presentation_kind() -> None:
    synthesizer = create_reference_component()
    local_uuid = "11111111-1111-4111-8111-111111111111"

    record = synthesizer.synthesize(
        RtgFederatedSynthesisRequest(
            intent_text="Deduplicate evidence.",
            reads=(
                RtgFederatedGraphRead(
                    graph_id="repo_twin",
                    status="executed",
                    query_name="repo_components_evidence_status",
                    citations=(
                        RtgFederatedCitation(
                            graph_id="repo_twin",
                            local_uuid=local_uuid,
                            label="First label",
                            kind="component",
                        ),
                        RtgFederatedCitation(
                            graph_id="repo_twin",
                            local_uuid=local_uuid,
                            label="Second label",
                            kind="evidence",
                        ),
                    ),
                ),
            ),
        )
    )

    assert record.citations == (
        RtgFederatedCitation(
            graph_id="repo_twin",
            local_uuid=local_uuid,
            label="First label",
            kind="component",
        ),
    )


@pytest.mark.parametrize("value", (float("nan"), float("inf")))
def test_rejects_non_finite_bridge_and_summary_values(value: float) -> None:
    synthesizer = create_reference_component()
    with pytest.raises(RtgFederatedSynthesisInvalid, match="confidence"):
        synthesizer.synthesize(
            RtgFederatedSynthesisRequest(
                intent_text="Invalid bridge confidence.",
                reads=(),
                bridges=(
                    RtgFederatedBridgeContext(
                        bridge_id="bridge_deadbeef0000000000",
                        bridge_type="related_context",
                        source_graph_id="repo_twin",
                        source_local_id="11111111-1111-4111-8111-111111111111",
                        target_graph_id="personal_ops",
                        target_local_id="22222222-2222-4222-8222-222222222222",
                        confidence=value,
                    ),
                ),
            )
        )
    with pytest.raises(RtgFederatedSynthesisInvalid, match="finite"):
        synthesizer.synthesize(
            RtgFederatedSynthesisRequest(
                intent_text="Invalid summary.",
                reads=(
                    RtgFederatedGraphRead(
                        graph_id="repo_twin",
                        status="executed",
                        query_name="repo_components_evidence_status",
                        summary={"score": value},
                    ),
                ),
            )
        )


def test_rejects_invalid_bridge_and_candidate_context() -> None:
    synthesizer = create_reference_component()
    with pytest.raises(RtgFederatedSynthesisInvalid, match="source_local_id"):
        synthesizer.synthesize(
            RtgFederatedSynthesisRequest(
                intent_text="Invalid bridge endpoint.",
                reads=(),
                bridges=(
                    RtgFederatedBridgeContext(
                        bridge_id="bridge_deadbeef0000000000",
                        bridge_type="related_context",
                        source_graph_id="repo_twin",
                        source_local_id="component.rtg.graph_registry",
                        target_graph_id="personal_ops",
                        target_local_id="22222222-2222-4222-8222-222222222222",
                        confidence=0.5,
                    ),
                ),
            )
        )
    with pytest.raises(RtgFederatedSynthesisInvalid, match="must be a boolean"):
        synthesizer.synthesize(
            RtgFederatedSynthesisRequest(
                intent_text="Invalid candidate permission.",
                reads=(),
                candidate_notices=(
                    RtgFederatedCandidateNotice(
                        candidate_id="candidate_deadbeef0000000000",
                        status="candidate_only",
                        traversal_permission="false",  # type: ignore[arg-type]
                        reason="review required",
                    ),
                ),
            )
        )


def test_synthesis_returns_isolated_records_without_input_mutation() -> None:
    synthesizer = create_reference_component()
    request = RtgFederatedSynthesisRequest(
        intent_text="Preserve source context.",
        reads=(
            RtgFederatedGraphRead(
                graph_id="repo_twin",
                status="executed",
                query_name="repo_components_evidence_status",
                summary={"nested": {"values": [1, 2]}},
                citations=(citation(),),
            ),
        ),
    )
    original = copy.deepcopy(request)

    record = synthesizer.synthesize(request)
    request.reads[0].summary["changed"] = True

    assert original.reads[0].summary == {"nested": {"values": [1, 2]}}
    assert record.reads[0].summary == {"nested": {"values": [1, 2]}}
    assert request.intent_text == original.intent_text


def test_synthesizer_does_not_expose_graph_or_bridge_mutation_operations() -> None:
    synthesizer = create_reference_component()

    for forbidden_name in (
        "execute_query",
        "put_anchor",
        "put_bridge",
        "promote_candidate",
        "run_mcp_server",
        "write",
    ):
        assert not hasattr(synthesizer, forbidden_name)
