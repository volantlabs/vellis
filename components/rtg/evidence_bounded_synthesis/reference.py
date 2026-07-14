from __future__ import annotations

from components.rtg.evidence_bounded_synthesis.implementation import (
    EvidenceBoundedRtgSynthesizer,
)
from components.rtg.evidence_bounded_synthesis.protocol import (
    RtgEvidenceBoundedSynthesisRequest,
    RtgEvidenceCitationRef,
    RtgSemanticClaimDraft,
    RtgSemanticSynthesisDraft,
)


class ReferenceSemanticDraftGenerator:
    """Deterministic generator used only to demonstrate the component boundary."""

    def generate(
        self,
        request: RtgEvidenceBoundedSynthesisRequest,
    ) -> RtgSemanticSynthesisDraft:
        claims: list[RtgSemanticClaimDraft] = []
        for read in request.source.reads:
            if read.status != "executed" or not read.citations:
                continue
            citation = read.citations[0]
            query_name = read.query_name or "graph_local"
            claims.append(
                RtgSemanticClaimDraft(
                    text=(
                        f"{read.graph_id} returned an executed {query_name} result with "
                        "graph-qualified evidence."
                    ),
                    kind="summary",
                    citation_refs=(
                        RtgEvidenceCitationRef(
                            graph_id=citation.graph_id,
                            local_uuid=citation.local_uuid,
                        ),
                    ),
                )
            )
        return RtgSemanticSynthesisDraft(claims=tuple(claims))


def create_reference_component() -> EvidenceBoundedRtgSynthesizer:
    return EvidenceBoundedRtgSynthesizer.open(ReferenceSemanticDraftGenerator())
