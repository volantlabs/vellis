from __future__ import annotations

import copy
import math
import re
from collections.abc import Iterable, Mapping
from uuid import UUID

from components.rtg.federated_synthesis.protocol import (
    JsonObject,
    JsonValue,
    RtgFederatedBridgeContext,
    RtgFederatedCandidateNotice,
    RtgFederatedCitation,
    RtgFederatedGraphRead,
    RtgFederatedSynthesisInvalid,
    RtgFederatedSynthesisRecord,
    RtgFederatedSynthesisRequest,
)

_IDENTIFIER_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")
_READ_STATUSES = {"executed", "unsupported", "skipped", "failed"}


class DeterministicRtgFederatedSynthesizer:
    """Deterministic read-only implementation of RTG federated synthesis."""

    def synthesize(
        self,
        request: RtgFederatedSynthesisRequest,
    ) -> RtgFederatedSynthesisRecord:
        normalized = _normalize_request(request)
        executed = tuple(read for read in normalized.reads if read.status == "executed")
        limitations = _limitations(normalized)
        status = _synthesis_status(executed, limitations)
        citations = _dedupe_citations(citation for read in executed for citation in read.citations)
        answer: JsonObject = {
            "summary": _summary_text(status, executed, normalized.reads, normalized.bridges),
            "executed_graph_count": len({read.graph_id for read in executed}),
            "planned_graph_count": len(normalized.reads),
            "bridge_count": len(normalized.bridges),
            "candidate_notice_count": len(normalized.candidate_notices),
            "sections": [_read_section(read) for read in normalized.reads],
        }
        return RtgFederatedSynthesisRecord(
            status=status,
            intent_text=normalized.intent_text,
            answer=answer,
            citations=citations,
            reads=normalized.reads,
            bridges=normalized.bridges,
            candidate_notices=normalized.candidate_notices,
            limitations=limitations,
        )


def _normalize_request(request: RtgFederatedSynthesisRequest) -> RtgFederatedSynthesisRequest:
    return RtgFederatedSynthesisRequest(
        intent_text=_validate_text(request.intent_text, "intent_text"),
        reads=tuple(_normalize_read(read) for read in request.reads),
        bridges=tuple(_normalize_bridge(bridge) for bridge in request.bridges),
        candidate_notices=tuple(
            _normalize_candidate_notice(notice) for notice in request.candidate_notices
        ),
    )


def _normalize_read(read: RtgFederatedGraphRead) -> RtgFederatedGraphRead:
    status = _validate_text(read.status, "read.status")
    if status not in _READ_STATUSES:
        raise RtgFederatedSynthesisInvalid(
            "read.status must be executed, unsupported, skipped, or failed"
        )
    graph_id = _validate_identifier(read.graph_id, "read.graph_id")
    citations = tuple(_normalize_citation(citation) for citation in read.citations)
    if any(citation.graph_id != graph_id for citation in citations):
        raise RtgFederatedSynthesisInvalid(
            "read citations must belong to the read.graph_id namespace"
        )
    return RtgFederatedGraphRead(
        graph_id=graph_id,
        status=status,
        query_name=None
        if read.query_name is None
        else _validate_identifier(read.query_name, "read.query_name"),
        summary=_validate_json_object(read.summary),
        citations=citations,
        notes=tuple(_validate_text(note, "read.notes") for note in read.notes),
    )


def _normalize_citation(citation: RtgFederatedCitation) -> RtgFederatedCitation:
    return RtgFederatedCitation(
        graph_id=_validate_identifier(citation.graph_id, "citation.graph_id"),
        local_uuid=_validate_uuid_text(citation.local_uuid, "citation.local_uuid"),
        label=None if citation.label is None else _validate_text(citation.label, "citation.label"),
        kind=_validate_identifier(citation.kind, "citation.kind"),
    )


def _normalize_bridge(bridge: RtgFederatedBridgeContext) -> RtgFederatedBridgeContext:
    confidence = bridge.confidence
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        raise RtgFederatedSynthesisInvalid("bridge confidence must be a number between 0 and 1")
    normalized_confidence = float(confidence)
    if not math.isfinite(normalized_confidence) or not 0 <= normalized_confidence <= 1:
        raise RtgFederatedSynthesisInvalid("bridge confidence must be a number between 0 and 1")
    source_graph_id = _validate_identifier(bridge.source_graph_id, "bridge.source_graph_id")
    target_graph_id = _validate_identifier(bridge.target_graph_id, "bridge.target_graph_id")
    if source_graph_id == target_graph_id:
        raise RtgFederatedSynthesisInvalid("bridge endpoints must belong to different graphs")
    return RtgFederatedBridgeContext(
        bridge_id=_validate_identifier(bridge.bridge_id, "bridge.bridge_id"),
        bridge_type=_validate_identifier(bridge.bridge_type, "bridge.bridge_type"),
        source_graph_id=source_graph_id,
        source_local_id=_validate_uuid_text(bridge.source_local_id, "bridge.source_local_id"),
        target_graph_id=target_graph_id,
        target_local_id=_validate_uuid_text(bridge.target_local_id, "bridge.target_local_id"),
        confidence=normalized_confidence,
    )


def _normalize_candidate_notice(
    notice: RtgFederatedCandidateNotice,
) -> RtgFederatedCandidateNotice:
    if not isinstance(notice.traversal_permission, bool):
        raise RtgFederatedSynthesisInvalid("candidate.traversal_permission must be a boolean")
    return RtgFederatedCandidateNotice(
        candidate_id=_validate_identifier(notice.candidate_id, "candidate.candidate_id"),
        status=_validate_identifier(notice.status, "candidate.status"),
        traversal_permission=notice.traversal_permission,
        reason=_validate_text(notice.reason, "candidate.reason"),
    )


def _limitations(request: RtgFederatedSynthesisRequest) -> tuple[str, ...]:
    limitations: list[str] = []
    for read in request.reads:
        if read.status == "executed":
            continue
        note = f"graph {read.graph_id} read was {read.status}"
        if read.notes:
            note = f"{note}: {'; '.join(read.notes)}"
        limitations.append(note)
    for notice in request.candidate_notices:
        if notice.traversal_permission:
            continue
        limitations.append(
            f"candidate {notice.candidate_id} not used for traversal: {notice.reason}"
        )
    return tuple(limitations)


def _synthesis_status(
    executed: tuple[RtgFederatedGraphRead, ...],
    limitations: tuple[str, ...],
) -> str:
    if not executed:
        return "no_supported_reads"
    if limitations:
        return "partial"
    return "complete"


def _dedupe_citations(
    citations: Iterable[RtgFederatedCitation],
) -> tuple[RtgFederatedCitation, ...]:
    deduped: dict[tuple[str, str], RtgFederatedCitation] = {}
    for citation in citations:
        key = (citation.graph_id, citation.local_uuid)
        deduped.setdefault(key, citation)
    return tuple(deduped[key] for key in sorted(deduped))


def _read_section(read: RtgFederatedGraphRead) -> JsonObject:
    return {
        "graph_id": read.graph_id,
        "status": read.status,
        "query_name": read.query_name,
        "summary": read.summary,
        "citation_count": len(read.citations),
        "notes": list(read.notes),
    }


def _summary_text(
    status: str,
    executed: tuple[RtgFederatedGraphRead, ...],
    reads: tuple[RtgFederatedGraphRead, ...],
    bridges: tuple[RtgFederatedBridgeContext, ...],
) -> str:
    if status == "no_supported_reads":
        return "No graph-local reads were executed for this federated request."
    return (
        f"Executed {len(executed)} of {len(reads)} graph-local read step(s) with "
        f"{len(bridges)} confirmed bridge hint(s)."
    )


def _validate_identifier(value: str, name: str) -> str:
    text = _validate_text(value, name)
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise RtgFederatedSynthesisInvalid(f"{name} must be an identifier")
    return text


def _validate_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgFederatedSynthesisInvalid(f"{name} must be a non-empty string")
    return value.strip()


def _validate_uuid_text(value: str, name: str) -> str:
    text = _validate_text(value, name)
    try:
        return str(UUID(text))
    except ValueError as error:
        raise RtgFederatedSynthesisInvalid(f"{name} must be a UUID") from error


def _validate_json_object(value: JsonObject) -> JsonObject:
    copied = copy.deepcopy(value)
    if not isinstance(copied, dict):
        raise RtgFederatedSynthesisInvalid("summary must be a JSON object")
    _validate_json_value(copied)
    return copied


def _validate_json_value(value: JsonValue) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RtgFederatedSynthesisInvalid("JSON object keys must be strings")
            _validate_json_value(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise RtgFederatedSynthesisInvalid("JSON numbers must be finite")
    if value is None or isinstance(value, str | int | float | bool):
        return
    raise RtgFederatedSynthesisInvalid("JSON values must be serializable")
