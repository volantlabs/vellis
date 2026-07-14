from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RtgFederatedCitation:
    graph_id: str
    local_uuid: str
    label: str | None = None
    kind: str = "record"


@dataclass(frozen=True, slots=True)
class RtgFederatedGraphRead:
    graph_id: str
    status: str
    query_name: str | None
    summary: JsonObject = field(default_factory=dict)
    citations: tuple[RtgFederatedCitation, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgFederatedBridgeContext:
    bridge_id: str
    bridge_type: str
    source_graph_id: str
    source_local_id: str
    target_graph_id: str
    target_local_id: str
    confidence: float


@dataclass(frozen=True, slots=True)
class RtgFederatedCandidateNotice:
    candidate_id: str
    status: str
    traversal_permission: bool
    reason: str


@dataclass(frozen=True, slots=True)
class RtgFederatedSynthesisRequest:
    intent_text: str
    reads: tuple[RtgFederatedGraphRead, ...]
    bridges: tuple[RtgFederatedBridgeContext, ...] = ()
    candidate_notices: tuple[RtgFederatedCandidateNotice, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgFederatedSynthesisRecord:
    status: str
    intent_text: str
    answer: JsonObject
    citations: tuple[RtgFederatedCitation, ...]
    reads: tuple[RtgFederatedGraphRead, ...]
    bridges: tuple[RtgFederatedBridgeContext, ...]
    candidate_notices: tuple[RtgFederatedCandidateNotice, ...]
    limitations: tuple[str, ...]


class RtgFederatedSynthesisInvalid(Exception):
    """A federated synthesis input is malformed."""


class RtgFederatedSynthesizer(Protocol):
    def synthesize(
        self,
        request: RtgFederatedSynthesisRequest,
    ) -> RtgFederatedSynthesisRecord:
        """Build a read-only synthesis record from graph-local reads and federation context."""
        ...
