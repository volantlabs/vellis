from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RtgGraphLocalReference:
    graph_id: str
    local_uuid: UUID


@dataclass(frozen=True, slots=True)
class RtgGraphBridgeDraft:
    bridge_type: str
    source: RtgGraphLocalReference
    target: RtgGraphLocalReference
    confidence: float
    asserted_at: str
    asserted_by: str
    provenance: tuple[RtgGraphLocalReference, ...]
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgGraphBridgeAssertion:
    bridge_id: str
    bridge_type: str
    source: RtgGraphLocalReference
    target: RtgGraphLocalReference
    confidence: float
    asserted_at: str
    asserted_by: str
    provenance: tuple[RtgGraphLocalReference, ...]
    metadata: JsonObject = field(default_factory=dict)
    status: str = "active"
    revoked_at: str | None = None
    revoked_by: str | None = None
    revocation_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RtgGraphBridgeCandidateDraft:
    bridge_type: str
    source: RtgGraphLocalReference
    target: RtgGraphLocalReference
    confidence: float
    proposed_at: str
    proposed_by: str
    evidence: tuple[RtgGraphLocalReference, ...]
    rationale: str
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgGraphBridgeCandidate:
    candidate_id: str
    bridge_type: str
    source: RtgGraphLocalReference
    target: RtgGraphLocalReference
    confidence: float
    proposed_at: str
    proposed_by: str
    evidence: tuple[RtgGraphLocalReference, ...]
    rationale: str
    metadata: JsonObject = field(default_factory=dict)
    status: str = "candidate_only"
    promoted_bridge_id: str | None = None
    rejected_at: str | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RtgGraphBridgeList:
    bridges: tuple[RtgGraphBridgeAssertion, ...]


@dataclass(frozen=True, slots=True)
class RtgGraphBridgeCandidateList:
    candidates: tuple[RtgGraphBridgeCandidate, ...]


class RtgGraphBridgeError(Exception):
    """Base class for RTG Graph Bridge errors."""


class RtgGraphBridgeInvalid(RtgGraphBridgeError):
    """A bridge assertion or lookup input is malformed."""


class RtgGraphBridgeNotFound(RtgGraphBridgeError):
    """A requested bridge assertion does not exist."""


class RtgGraphBridge(Protocol):
    @classmethod
    def empty(cls) -> RtgGraphBridge:
        """Create an empty bridge store."""
        ...

    def put_bridge(self, bridge: RtgGraphBridgeDraft) -> RtgGraphBridgeAssertion:
        """Create or replace one active bridge assertion."""
        ...

    def get_bridge(self, bridge_id: str) -> RtgGraphBridgeAssertion:
        """Return one bridge assertion by id."""
        ...

    def list_bridges(self, status: str | None = None) -> RtgGraphBridgeList:
        """List bridge assertions, optionally filtered by status."""
        ...

    def find_bridges(
        self,
        reference: RtgGraphLocalReference,
        status: str | None = "active",
    ) -> RtgGraphBridgeList:
        """List bridge assertions connected to a graph-local reference."""
        ...

    def revoke_bridge(
        self,
        bridge_id: str,
        *,
        revoked_at: str,
        revoked_by: str,
        reason: str,
    ) -> RtgGraphBridgeAssertion:
        """Mark a bridge assertion as revoked."""
        ...

    def put_candidate(self, candidate: RtgGraphBridgeCandidateDraft) -> RtgGraphBridgeCandidate:
        """Create or replace one bridge candidate."""
        ...

    def get_candidate(self, candidate_id: str) -> RtgGraphBridgeCandidate:
        """Return one bridge candidate by id."""
        ...

    def list_candidates(self, status: str | None = "candidate_only") -> RtgGraphBridgeCandidateList:
        """List bridge candidates, optionally filtered by status."""
        ...

    def find_candidates(
        self,
        reference: RtgGraphLocalReference,
        status: str | None = "candidate_only",
    ) -> RtgGraphBridgeCandidateList:
        """List bridge candidates connected to a graph-local reference."""
        ...

    def promote_candidate(
        self,
        candidate_id: str,
        *,
        asserted_at: str,
        asserted_by: str,
    ) -> RtgGraphBridgeAssertion:
        """Promote a candidate into an active bridge assertion."""
        ...

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        rejected_at: str,
        rejected_by: str,
        reason: str,
    ) -> RtgGraphBridgeCandidate:
        """Reject a bridge candidate without creating a bridge assertion."""
        ...
