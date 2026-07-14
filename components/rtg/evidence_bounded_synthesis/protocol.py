from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from components.rtg.federated_synthesis import (
    RtgFederatedCitation,
    RtgFederatedSynthesisRecord,
)


@dataclass(frozen=True, slots=True)
class RtgEvidenceCitationRef:
    graph_id: str
    local_uuid: str


@dataclass(frozen=True, slots=True)
class RtgSemanticClaimDraft:
    text: str
    kind: str
    citation_refs: tuple[RtgEvidenceCitationRef, ...]
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class RtgSemanticSynthesisDraft:
    claims: tuple[RtgSemanticClaimDraft, ...]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgEvidenceBoundedSynthesisRequest:
    intent_text: str
    source: RtgFederatedSynthesisRecord


@dataclass(frozen=True, slots=True)
class RtgEvidenceBoundedClaim:
    text: str
    kind: str
    citations: tuple[RtgFederatedCitation, ...]
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class RtgEvidenceBoundedSynthesisRecord:
    status: str
    intent_text: str
    source_status: str
    claims: tuple[RtgEvidenceBoundedClaim, ...]
    citations: tuple[RtgFederatedCitation, ...]
    limitations: tuple[str, ...]
    entailment_status: str = "not_verified"


class RtgEvidenceBoundedSynthesisInvalid(Exception):
    """An evidence-bounded synthesis request or generated draft is malformed."""


class RtgSemanticDraftGenerator(Protocol):
    def generate(
        self,
        request: RtgEvidenceBoundedSynthesisRequest,
    ) -> RtgSemanticSynthesisDraft:
        """Propose untrusted claims from an isolated evidence envelope treated as read-only."""
        ...


class RtgEvidenceBoundedSynthesizer(Protocol):
    def synthesize(
        self,
        request: RtgEvidenceBoundedSynthesisRequest,
    ) -> RtgEvidenceBoundedSynthesisRecord:
        """Generate and validate semantic claims against deterministic federated evidence."""
        ...
