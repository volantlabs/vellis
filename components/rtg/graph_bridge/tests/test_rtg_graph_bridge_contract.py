from __future__ import annotations

from uuid import uuid4

from components.rtg.graph_bridge import (
    InMemoryRtgGraphBridge,
    RtgGraphBridgeCandidateDraft,
    RtgGraphBridgeDraft,
    RtgGraphBridgeInvalid,
    RtgGraphBridgeNotFound,
    RtgGraphLocalReference,
)
from components.rtg.graph_bridge.reference import create_reference_component

MODEL_EVIDENCE = {
    "PutBridgeContractVerification": (
        "test_bridge_stores_lists_fetches_and_returns_copies",
        "test_bridge_identity_is_deterministic_and_direction_sensitive",
        "test_bridge_validates_graph_qualified_cross_graph_references",
        "test_bridge_rejects_non_finite_numbers_without_replacing_records",
    ),
    "GetBridgeContractVerification": (
        "test_bridge_stores_lists_fetches_and_returns_copies",
        "test_bridge_reports_missing_or_malformed_ids",
    ),
    "ListBridgesContractVerification": (
        "test_empty_bridge_store_has_no_records",
        "test_bridge_stores_lists_fetches_and_returns_copies",
        "test_bridge_identity_is_deterministic_and_direction_sensitive",
        "test_bridge_rejects_invalid_filters_and_references_without_mutation",
    ),
    "FindBridgesContractVerification": (
        "test_bridge_finds_connected_assertions_and_filters_revoked_by_default",
        "test_bridge_rejects_invalid_filters_and_references_without_mutation",
    ),
    "RevokeBridgeContractVerification": (
        "test_bridge_finds_connected_assertions_and_filters_revoked_by_default",
        "test_bridge_mutations_are_failure_atomic",
    ),
    "PutCandidateContractVerification": (
        "test_bridge_candidates_are_separate_from_confirmed_bridges",
        "test_bridge_candidate_identity_is_deterministic_and_evidence_sensitive",
        "test_bridge_validates_candidate_shape",
        "test_bridge_rejects_non_finite_numbers_without_replacing_records",
    ),
    "GetCandidateContractVerification": (
        "test_bridge_candidates_are_separate_from_confirmed_bridges",
        "test_bridge_reports_missing_or_malformed_ids",
    ),
    "ListCandidatesContractVerification": (
        "test_empty_bridge_store_has_no_records",
        "test_bridge_candidates_are_separate_from_confirmed_bridges",
        "test_bridge_candidate_can_be_promoted_or_rejected",
        "test_bridge_rejects_invalid_filters_and_references_without_mutation",
    ),
    "FindCandidatesContractVerification": (
        "test_bridge_candidates_are_separate_from_confirmed_bridges",
        "test_bridge_rejects_invalid_filters_and_references_without_mutation",
    ),
    "PromoteCandidateContractVerification": (
        "test_bridge_candidate_can_be_promoted_or_rejected",
        "test_bridge_mutations_are_failure_atomic",
        "test_candidate_review_rejects_repeated_transitions_without_mutation",
    ),
    "RejectCandidateContractVerification": (
        "test_bridge_candidate_can_be_promoted_or_rejected",
        "test_candidate_review_rejects_repeated_transitions_without_mutation",
    ),
    "CreateEmptyRtgGraphBridgeContractVerification": ("test_empty_bridge_store_has_no_records",),
    "RtgGraphBridgeBoundaryVerification": (
        "test_empty_bridge_store_has_no_records",
        "test_bridge_stores_lists_fetches_and_returns_copies",
        "test_bridge_identity_is_deterministic_and_direction_sensitive",
        "test_bridge_finds_connected_assertions_and_filters_revoked_by_default",
        "test_bridge_candidates_are_separate_from_confirmed_bridges",
        "test_bridge_candidate_identity_is_deterministic_and_evidence_sensitive",
        "test_bridge_candidate_can_be_promoted_or_rejected",
        "test_bridge_validates_graph_qualified_cross_graph_references",
        "test_bridge_validates_candidate_shape",
        "test_bridge_surface_does_not_expose_adjacent_component_operations",
    ),
}


def repo_ref() -> RtgGraphLocalReference:
    return RtgGraphLocalReference(graph_id="repo_twin", local_uuid=uuid4())


def personal_ref() -> RtgGraphLocalReference:
    return RtgGraphLocalReference(graph_id="personal_ops", local_uuid=uuid4())


def evidence_ref() -> RtgGraphLocalReference:
    return RtgGraphLocalReference(graph_id="repo_twin", local_uuid=uuid4())


def bridge_draft(
    *,
    source: RtgGraphLocalReference | None = None,
    target: RtgGraphLocalReference | None = None,
    provenance: tuple[RtgGraphLocalReference, ...] | None = None,
    confidence: float = 0.92,
) -> RtgGraphBridgeDraft:
    return RtgGraphBridgeDraft(
        bridge_type="same_entity",
        source=source or repo_ref(),
        target=target or personal_ref(),
        confidence=confidence,
        asserted_at="2026-07-09T00:00:00Z",
        asserted_by="agent.codex",
        provenance=provenance if provenance is not None else (evidence_ref(),),
        metadata={"rationale": "same display name and corroborating evidence"},
    )


def candidate_draft(
    *,
    source: RtgGraphLocalReference | None = None,
    target: RtgGraphLocalReference | None = None,
    evidence: tuple[RtgGraphLocalReference, ...] | None = None,
    confidence: float = 0.72,
) -> RtgGraphBridgeCandidateDraft:
    return RtgGraphBridgeCandidateDraft(
        bridge_type="same_entity",
        source=source or repo_ref(),
        target=target or personal_ref(),
        confidence=confidence,
        proposed_at="2026-07-09T00:00:00Z",
        proposed_by="agent.codex",
        evidence=evidence if evidence is not None else (evidence_ref(),),
        rationale="same label and overlapping context",
        metadata={"review_note": "candidate requires human confirmation"},
    )


def test_empty_bridge_store_has_no_records() -> None:
    bridge = create_reference_component()

    assert bridge.list_bridges().bridges == ()
    assert bridge.list_candidates(status=None).candidates == ()


def test_bridge_stores_lists_fetches_and_returns_copies() -> None:
    bridge = create_reference_component()
    assertion = bridge.put_bridge(bridge_draft())
    assertion.metadata["mutated"] = True

    fetched = bridge.get_bridge(assertion.bridge_id)
    listed = bridge.list_bridges().bridges
    listed[0].metadata["listed_mutation"] = True

    assert fetched.bridge_id == assertion.bridge_id
    assert fetched.status == "active"
    assert fetched.metadata == {"rationale": "same display name and corroborating evidence"}
    assert bridge.get_bridge(assertion.bridge_id).metadata == {
        "rationale": "same display name and corroborating evidence"
    }


def test_bridge_identity_is_deterministic_and_direction_sensitive() -> None:
    bridge = create_reference_component()
    source = repo_ref()
    target = personal_ref()
    provenance = (evidence_ref(),)

    first = bridge.put_bridge(bridge_draft(source=source, target=target, provenance=provenance))
    replacement = bridge.put_bridge(
        RtgGraphBridgeDraft(
            bridge_type="same_entity",
            source=source,
            target=target,
            confidence=0.5,
            asserted_at="2026-07-09T01:00:00Z",
            asserted_by="agent.codex",
            provenance=provenance,
            metadata={"rationale": "replacement"},
        )
    )
    reverse = bridge.put_bridge(bridge_draft(source=target, target=source, provenance=provenance))

    assert replacement.bridge_id == first.bridge_id
    assert replacement.confidence == 0.5
    assert reverse.bridge_id != first.bridge_id
    assert [item.bridge_id for item in bridge.list_bridges().bridges] == sorted(
        [first.bridge_id, reverse.bridge_id]
    )


def test_bridge_finds_connected_assertions_and_filters_revoked_by_default() -> None:
    bridge = create_reference_component()
    source = repo_ref()
    assertion = bridge.put_bridge(bridge_draft(source=source))

    assert bridge.find_bridges(source).bridges == (assertion,)

    revoked = bridge.revoke_bridge(
        assertion.bridge_id,
        revoked_at="2026-07-09T02:00:00Z",
        revoked_by="agent.codex",
        reason="identity evidence was withdrawn",
    )

    assert revoked.status == "revoked"
    assert bridge.find_bridges(source).bridges == ()
    assert bridge.find_bridges(source, status=None).bridges == (revoked,)
    assert bridge.list_bridges(status="revoked").bridges == (revoked,)


def test_bridge_candidates_are_separate_from_confirmed_bridges() -> None:
    bridge = create_reference_component()
    source = repo_ref()
    candidate = bridge.put_candidate(candidate_draft(source=source))
    candidate.metadata["mutated"] = True

    fetched = bridge.get_candidate(candidate.candidate_id)
    listed = bridge.list_candidates().candidates
    listed[0].metadata["listed_mutation"] = True

    assert candidate.status == "candidate_only"
    assert fetched.candidate_id == candidate.candidate_id
    assert bridge.list_bridges().bridges == ()
    assert bridge.find_bridges(source).bridges == ()
    assert bridge.find_candidates(source).candidates[0].candidate_id == candidate.candidate_id
    assert bridge.list_candidates().candidates[0].metadata == {
        "review_note": "candidate requires human confirmation"
    }


def test_bridge_candidate_identity_is_deterministic_and_evidence_sensitive() -> None:
    bridge = create_reference_component()
    source = repo_ref()
    target = personal_ref()
    evidence = (evidence_ref(),)

    first = bridge.put_candidate(candidate_draft(source=source, target=target, evidence=evidence))
    replacement = bridge.put_candidate(
        RtgGraphBridgeCandidateDraft(
            bridge_type="same_entity",
            source=source,
            target=target,
            confidence=0.4,
            proposed_at="2026-07-09T01:00:00Z",
            proposed_by="agent.codex",
            evidence=evidence,
            rationale="replacement candidate",
        )
    )
    second_evidence = bridge.put_candidate(
        candidate_draft(source=source, target=target, evidence=(evidence_ref(),))
    )

    assert replacement.candidate_id == first.candidate_id
    assert replacement.confidence == 0.4
    assert second_evidence.candidate_id != first.candidate_id


def test_bridge_candidate_can_be_promoted_or_rejected() -> None:
    bridge = create_reference_component()
    promoted_candidate = bridge.put_candidate(candidate_draft())
    rejected_candidate = bridge.put_candidate(candidate_draft(source=repo_ref()))

    assertion = bridge.promote_candidate(
        promoted_candidate.candidate_id,
        asserted_at="2026-07-09T02:00:00Z",
        asserted_by="agent.codex",
    )
    rejected = bridge.reject_candidate(
        rejected_candidate.candidate_id,
        rejected_at="2026-07-09T03:00:00Z",
        rejected_by="agent.codex",
        reason="not enough identity evidence",
    )

    assert assertion.source == promoted_candidate.source
    assert assertion.target == promoted_candidate.target
    assert assertion.metadata["promoted_from_candidate_id"] == promoted_candidate.candidate_id
    assert bridge.list_candidates(status="promoted").candidates[0].promoted_bridge_id == (
        assertion.bridge_id
    )
    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "not enough identity evidence"
    assert bridge.list_candidates().candidates == ()
    assert len(bridge.list_candidates(status=None).candidates) == 2


def test_bridge_validates_graph_qualified_cross_graph_references() -> None:
    bridge = create_reference_component()
    source = repo_ref()
    invalid_drafts = (
        bridge_draft(target=RtgGraphLocalReference(graph_id="repo_twin", local_uuid=uuid4())),
        bridge_draft(source=RtgGraphLocalReference(graph_id="bad-id", local_uuid=uuid4())),
        bridge_draft(source=RtgGraphLocalReference(graph_id="repo_twin", local_uuid="bad")),  # type: ignore[arg-type]
        bridge_draft(provenance=()),
        bridge_draft(confidence=-0.1),
        bridge_draft(confidence=1.1),
        bridge_draft(
            source=source,
            target=personal_ref(),
            provenance=(source,),
            confidence=True,  # type: ignore[arg-type]
        ),
        RtgGraphBridgeDraft(
            bridge_type="same_entity",
            source=source,
            target=personal_ref(),
            confidence=0.5,
            asserted_at="2026-07-09T00:00:00Z",
            asserted_by="agent.codex",
            provenance=(evidence_ref(),),
            metadata={"bad": object()},  # type: ignore[dict-item]
        ),
    )

    for draft in invalid_drafts:
        try:
            bridge.put_bridge(draft)
        except RtgGraphBridgeInvalid:
            pass
        else:
            raise AssertionError(f"invalid bridge should fail: {draft}")


def test_bridge_validates_candidate_shape() -> None:
    bridge = create_reference_component()
    source = repo_ref()
    invalid_candidates = (
        candidate_draft(target=RtgGraphLocalReference(graph_id="repo_twin", local_uuid=uuid4())),
        candidate_draft(source=RtgGraphLocalReference(graph_id="bad-id", local_uuid=uuid4())),
        candidate_draft(evidence=()),
        candidate_draft(confidence=-0.1),
        candidate_draft(confidence=1.1),
        RtgGraphBridgeCandidateDraft(
            bridge_type="same_entity",
            source=source,
            target=personal_ref(),
            confidence=0.5,
            proposed_at="2026-07-09T00:00:00Z",
            proposed_by="agent.codex",
            evidence=(evidence_ref(),),
            rationale="",
        ),
        RtgGraphBridgeCandidateDraft(
            bridge_type="same_entity",
            source=source,
            target=personal_ref(),
            confidence=0.5,
            proposed_at="2026-07-09T00:00:00Z",
            proposed_by="agent.codex",
            evidence=(evidence_ref(),),
            rationale="bad metadata",
            metadata={"bad": object()},  # type: ignore[dict-item]
        ),
    )

    for candidate in invalid_candidates:
        try:
            bridge.put_candidate(candidate)
        except RtgGraphBridgeInvalid:
            pass
        else:
            raise AssertionError(f"invalid candidate should fail: {candidate}")


def test_bridge_rejects_non_finite_numbers_without_replacing_records() -> None:
    bridge = create_reference_component()
    source = repo_ref()
    target = personal_ref()
    provenance = (evidence_ref(),)
    assertion = bridge.put_bridge(bridge_draft(source=source, target=target, provenance=provenance))
    candidate = bridge.put_candidate(
        candidate_draft(source=source, target=target, evidence=provenance)
    )

    for number in (float("nan"), float("inf"), float("-inf")):
        invalid_bridge = bridge_draft(
            source=source,
            target=target,
            provenance=provenance,
            confidence=number,
        )
        invalid_candidate = candidate_draft(
            source=source,
            target=target,
            evidence=provenance,
            confidence=number,
        )
        try:
            bridge.put_bridge(invalid_bridge)
        except RtgGraphBridgeInvalid:
            pass
        else:
            raise AssertionError("non-finite bridge confidence should fail")
        try:
            bridge.put_candidate(invalid_candidate)
        except RtgGraphBridgeInvalid:
            pass
        else:
            raise AssertionError("non-finite candidate confidence should fail")

    invalid_metadata = bridge_draft(source=source, target=target, provenance=provenance)
    invalid_metadata.metadata["number"] = float("nan")
    try:
        bridge.put_bridge(invalid_metadata)
    except RtgGraphBridgeInvalid:
        pass
    else:
        raise AssertionError("non-finite metadata should fail")

    assert bridge.get_bridge(assertion.bridge_id) == assertion
    assert bridge.get_candidate(candidate.candidate_id) == candidate


def test_bridge_mutations_are_failure_atomic() -> None:
    bridge = create_reference_component()
    assertion = bridge.put_bridge(bridge_draft())
    candidate = bridge.put_candidate(candidate_draft())
    before_bridges = bridge.list_bridges()
    before_candidates = bridge.list_candidates(status=None)

    try:
        bridge.revoke_bridge(
            assertion.bridge_id,
            revoked_at=" ",
            revoked_by="agent.codex",
            reason="invalid timestamp",
        )
    except RtgGraphBridgeInvalid:
        pass
    else:
        raise AssertionError("invalid revocation metadata should fail")

    try:
        bridge.promote_candidate(
            candidate.candidate_id,
            asserted_at=" ",
            asserted_by="agent.codex",
        )
    except RtgGraphBridgeInvalid:
        pass
    else:
        raise AssertionError("invalid promotion metadata should fail")

    assert bridge.list_bridges() == before_bridges
    assert bridge.list_candidates(status=None) == before_candidates


def test_candidate_review_rejects_repeated_transitions_without_mutation() -> None:
    bridge = create_reference_component()
    promoted = bridge.put_candidate(candidate_draft())
    rejected = bridge.put_candidate(candidate_draft(source=repo_ref()))
    bridge.promote_candidate(
        promoted.candidate_id,
        asserted_at="2026-07-09T02:00:00Z",
        asserted_by="agent.codex",
    )
    bridge.reject_candidate(
        rejected.candidate_id,
        rejected_at="2026-07-09T03:00:00Z",
        rejected_by="agent.codex",
        reason="not enough evidence",
    )
    before_bridges = bridge.list_bridges()
    before_candidates = bridge.list_candidates(status=None)

    for candidate_id in (promoted.candidate_id, rejected.candidate_id):
        try:
            bridge.promote_candidate(
                candidate_id,
                asserted_at="2026-07-09T04:00:00Z",
                asserted_by="agent.codex",
            )
        except RtgGraphBridgeInvalid:
            pass
        else:
            raise AssertionError("reviewed candidate should not be promoted again")

    assert bridge.list_bridges() == before_bridges
    assert bridge.list_candidates(status=None) == before_candidates


def test_bridge_rejects_invalid_filters_and_references_without_mutation() -> None:
    bridge = create_reference_component()
    bridge.put_bridge(bridge_draft())
    bridge.put_candidate(candidate_draft())
    before_bridges = bridge.list_bridges()
    before_candidates = bridge.list_candidates(status=None)

    invalid_calls = (
        lambda: bridge.list_bridges(status="unknown"),
        lambda: bridge.find_bridges(RtgGraphLocalReference(graph_id="bad-id", local_uuid=uuid4())),
        lambda: bridge.list_candidates(status="active"),
        lambda: bridge.find_candidates(
            RtgGraphLocalReference(graph_id="bad-id", local_uuid=uuid4())
        ),
    )
    for call in invalid_calls:
        try:
            call()
        except RtgGraphBridgeInvalid:
            pass
        else:
            raise AssertionError("invalid filter or reference should fail")

    assert bridge.list_bridges() == before_bridges
    assert bridge.list_candidates(status=None) == before_candidates


def test_bridge_reports_missing_or_malformed_ids() -> None:
    bridge = create_reference_component()

    try:
        bridge.get_bridge("bridge_bad")
    except RtgGraphBridgeInvalid:
        pass
    else:
        raise AssertionError("malformed bridge id should fail")

    try:
        bridge.get_bridge("bridge_00000000000000000000")
    except RtgGraphBridgeNotFound:
        pass
    else:
        raise AssertionError("missing bridge id should fail")

    try:
        bridge.promote_candidate(
            "candidate_bad",
            asserted_at="2026-07-09T00:00:00Z",
            asserted_by="agent.codex",
        )
    except RtgGraphBridgeInvalid:
        pass
    else:
        raise AssertionError("malformed candidate id should fail")

    try:
        bridge.get_candidate("candidate_00000000000000000000")
    except RtgGraphBridgeNotFound:
        pass
    else:
        raise AssertionError("missing candidate id should fail")


def test_bridge_surface_does_not_expose_adjacent_component_operations() -> None:
    bridge = InMemoryRtgGraphBridge.empty()

    for forbidden_name in (
        "execute",
        "put_anchor",
        "put_link",
        "compile_intent",
        "validate_live_graph_changes",
        "stage_schema_migration",
        "run_mcp_server",
        "query",
    ):
        assert not hasattr(bridge, forbidden_name)
