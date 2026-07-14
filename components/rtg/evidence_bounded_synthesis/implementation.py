from __future__ import annotations

import copy
import re
from uuid import UUID

from components.rtg.evidence_bounded_synthesis.protocol import (
    RtgEvidenceBoundedClaim,
    RtgEvidenceBoundedSynthesisInvalid,
    RtgEvidenceBoundedSynthesisRecord,
    RtgEvidenceBoundedSynthesisRequest,
    RtgEvidenceCitationRef,
    RtgSemanticClaimDraft,
    RtgSemanticDraftGenerator,
    RtgSemanticSynthesisDraft,
)
from components.rtg.federated_synthesis import (
    RtgFederatedCitation,
    RtgFederatedSynthesisRecord,
)

_CLAIM_KINDS = {"summary", "comparison", "inference"}
_SOURCE_STATUSES = {"complete", "partial", "no_supported_reads"}
_IDENTIFIER_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")


class EvidenceBoundedRtgSynthesizer:
    """Fail-closed semantic synthesis over deterministic federated evidence."""

    def __init__(self, generator: RtgSemanticDraftGenerator) -> None:
        self._generator = generator

    @classmethod
    def open(cls, generator: RtgSemanticDraftGenerator) -> EvidenceBoundedRtgSynthesizer:
        if not callable(getattr(generator, "generate", None)):
            raise RtgEvidenceBoundedSynthesisInvalid("generator must provide generate")
        return cls(generator)

    def synthesize(
        self,
        request: RtgEvidenceBoundedSynthesisRequest,
    ) -> RtgEvidenceBoundedSynthesisRecord:
        normalized = _normalize_request(request)
        source_citations = _source_citation_catalog(normalized.source)
        source_limitations = tuple(
            _validate_text(item, "source limitation") for item in normalized.source.limitations
        )
        if normalized.source.status == "no_supported_reads" or not source_citations:
            reason = (
                "deterministic source has no supported reads"
                if normalized.source.status == "no_supported_reads"
                else "deterministic source has no graph-qualified citations"
            )
            return _record(
                normalized,
                claims=(),
                citations=(),
                limitations=_dedupe_text((*source_limitations, reason)),
            )

        generated = self._generator.generate(copy.deepcopy(normalized))
        if not isinstance(generated, RtgSemanticSynthesisDraft):
            raise RtgEvidenceBoundedSynthesisInvalid(
                "generator must return RtgSemanticSynthesisDraft"
            )
        claims = tuple(
            _normalize_claim(claim, source_citations) for claim in generated.claims
        )
        generator_limitations = tuple(
            _validate_text(item, "generator limitation") for item in generated.limitations
        )
        limitations = _dedupe_text((*source_limitations, *generator_limitations))
        if not claims:
            limitations = _dedupe_text(
                (*limitations, "semantic generator returned no supported claims")
            )
        citations = _dedupe_citations(
            citation for claim in claims for citation in claim.citations
        )
        return _record(
            normalized,
            claims=claims,
            citations=citations,
            limitations=limitations,
        )


def _normalize_request(
    request: RtgEvidenceBoundedSynthesisRequest,
) -> RtgEvidenceBoundedSynthesisRequest:
    if not isinstance(request, RtgEvidenceBoundedSynthesisRequest):
        raise RtgEvidenceBoundedSynthesisInvalid(
            "request must be RtgEvidenceBoundedSynthesisRequest"
        )
    intent_text = _validate_text(request.intent_text, "intent_text")
    source = request.source
    if not isinstance(source, RtgFederatedSynthesisRecord):
        raise RtgEvidenceBoundedSynthesisInvalid(
            "source must be RtgFederatedSynthesisRecord"
        )
    source_intent = _validate_text(source.intent_text, "source.intent_text")
    if intent_text != source_intent:
        raise RtgEvidenceBoundedSynthesisInvalid(
            "request intent_text must match source intent_text"
        )
    if source.status not in _SOURCE_STATUSES:
        raise RtgEvidenceBoundedSynthesisInvalid(
            "source status must be complete, partial, or no_supported_reads"
        )
    return RtgEvidenceBoundedSynthesisRequest(
        intent_text=intent_text,
        source=copy.deepcopy(source),
    )


def _source_citation_catalog(
    source: RtgFederatedSynthesisRecord,
) -> dict[tuple[str, str], RtgFederatedCitation]:
    catalog: dict[tuple[str, str], RtgFederatedCitation] = {}
    for citation in source.citations:
        normalized = _normalize_citation(citation)
        catalog.setdefault((normalized.graph_id, normalized.local_uuid), normalized)
    return catalog


def _normalize_claim(
    claim: RtgSemanticClaimDraft,
    source_citations: dict[tuple[str, str], RtgFederatedCitation],
) -> RtgEvidenceBoundedClaim:
    if not isinstance(claim, RtgSemanticClaimDraft):
        raise RtgEvidenceBoundedSynthesisInvalid(
            "generator claims must be RtgSemanticClaimDraft values"
        )
    text = _validate_text(claim.text, "claim.text")
    kind = _validate_identifier(claim.kind, "claim.kind")
    if kind not in _CLAIM_KINDS:
        raise RtgEvidenceBoundedSynthesisInvalid(
            "claim.kind must be summary, comparison, or inference"
        )
    uncertainty = (
        None
        if claim.uncertainty is None
        else _validate_text(claim.uncertainty, "claim.uncertainty")
    )
    if kind == "inference" and uncertainty is None:
        raise RtgEvidenceBoundedSynthesisInvalid(
            "inference claims must disclose uncertainty"
        )
    citations: list[RtgFederatedCitation] = []
    seen: set[tuple[str, str]] = set()
    for reference in claim.citation_refs:
        key = _normalize_reference(reference)
        if key in seen:
            continue
        citation = source_citations.get(key)
        if citation is None:
            raise RtgEvidenceBoundedSynthesisInvalid(
                f"claim citation is absent from source evidence: {key[0]}:{key[1]}"
            )
        seen.add(key)
        citations.append(citation)
    if not citations:
        raise RtgEvidenceBoundedSynthesisInvalid(
            "every claim must cite at least one source evidence record"
        )
    if kind == "comparison" and len({citation.graph_id for citation in citations}) < 2:
        raise RtgEvidenceBoundedSynthesisInvalid(
            "comparison claims must cite at least two graph namespaces"
        )
    return RtgEvidenceBoundedClaim(
        text=text,
        kind=kind,
        citations=tuple(citations),
        uncertainty=uncertainty,
    )


def _normalize_reference(reference: RtgEvidenceCitationRef) -> tuple[str, str]:
    if not isinstance(reference, RtgEvidenceCitationRef):
        raise RtgEvidenceBoundedSynthesisInvalid(
            "claim citation_refs must be RtgEvidenceCitationRef values"
        )
    return (
        _validate_identifier(reference.graph_id, "citation_ref.graph_id"),
        _validate_uuid(reference.local_uuid, "citation_ref.local_uuid"),
    )


def _normalize_citation(citation: RtgFederatedCitation) -> RtgFederatedCitation:
    if not isinstance(citation, RtgFederatedCitation):
        raise RtgEvidenceBoundedSynthesisInvalid(
            "source citations must be RtgFederatedCitation values"
        )
    return RtgFederatedCitation(
        graph_id=_validate_identifier(citation.graph_id, "source citation.graph_id"),
        local_uuid=_validate_uuid(citation.local_uuid, "source citation.local_uuid"),
        label=None
        if citation.label is None
        else _validate_text(citation.label, "source citation.label"),
        kind=_validate_identifier(citation.kind, "source citation.kind"),
    )


def _record(
    request: RtgEvidenceBoundedSynthesisRequest,
    *,
    claims: tuple[RtgEvidenceBoundedClaim, ...],
    citations: tuple[RtgFederatedCitation, ...],
    limitations: tuple[str, ...],
) -> RtgEvidenceBoundedSynthesisRecord:
    if not claims:
        status = "no_supported_claims"
    elif request.source.status != "complete" or limitations:
        status = "partial"
    else:
        status = "complete"
    return RtgEvidenceBoundedSynthesisRecord(
        status=status,
        intent_text=request.intent_text,
        source_status=request.source.status,
        claims=claims,
        citations=citations,
        limitations=limitations,
        entailment_status="not_verified",
    )


def _dedupe_citations(citations: object) -> tuple[RtgFederatedCitation, ...]:
    deduped: dict[tuple[str, str], RtgFederatedCitation] = {}
    for citation in citations:  # type: ignore[assignment]
        deduped.setdefault((citation.graph_id, citation.local_uuid), citation)
    return tuple(deduped.values())


def _dedupe_text(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _validate_identifier(value: str, name: str) -> str:
    text = _validate_text(value, name)
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise RtgEvidenceBoundedSynthesisInvalid(f"{name} must be an identifier")
    return text


def _validate_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgEvidenceBoundedSynthesisInvalid(f"{name} must be a non-empty string")
    return value.strip()


def _validate_uuid(value: str, name: str) -> str:
    text = _validate_text(value, name)
    try:
        return str(UUID(text))
    except ValueError as error:
        raise RtgEvidenceBoundedSynthesisInvalid(f"{name} must be a UUID") from error
