from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping
from uuid import UUID

from components.rtg.graph_bridge.protocol import (
    JsonObject,
    JsonValue,
    RtgGraphBridgeAssertion,
    RtgGraphBridgeCandidate,
    RtgGraphBridgeCandidateDraft,
    RtgGraphBridgeCandidateList,
    RtgGraphBridgeDraft,
    RtgGraphBridgeInvalid,
    RtgGraphBridgeList,
    RtgGraphBridgeNotFound,
    RtgGraphLocalReference,
)


class InMemoryRtgGraphBridge:
    """In-memory implementation of the RTG Graph Bridge component."""

    def __init__(self) -> None:
        self._bridges: dict[str, RtgGraphBridgeAssertion] = {}
        self._candidates: dict[str, RtgGraphBridgeCandidate] = {}

    @classmethod
    def empty(cls) -> InMemoryRtgGraphBridge:
        return cls()

    def put_bridge(self, bridge: RtgGraphBridgeDraft) -> RtgGraphBridgeAssertion:
        normalized = _normalize_draft(bridge)
        bridge_id = _derive_bridge_id(normalized)
        assertion = RtgGraphBridgeAssertion(
            bridge_id=bridge_id,
            bridge_type=normalized.bridge_type,
            source=normalized.source,
            target=normalized.target,
            confidence=normalized.confidence,
            asserted_at=normalized.asserted_at,
            asserted_by=normalized.asserted_by,
            provenance=normalized.provenance,
            metadata=normalized.metadata,
        )
        self._bridges[bridge_id] = assertion
        return _copy_assertion(assertion)

    def get_bridge(self, bridge_id: str) -> RtgGraphBridgeAssertion:
        normalized_id = _validate_bridge_id(bridge_id)
        try:
            assertion = self._bridges[normalized_id]
        except KeyError as error:
            raise RtgGraphBridgeNotFound(normalized_id) from error
        return _copy_assertion(assertion)

    def list_bridges(self, status: str | None = None) -> RtgGraphBridgeList:
        normalized_status = None if status is None else _validate_status(status)
        return RtgGraphBridgeList(
            bridges=tuple(
                _copy_assertion(assertion)
                for assertion in sorted(self._bridges.values(), key=lambda item: item.bridge_id)
                if normalized_status is None or assertion.status == normalized_status
            )
        )

    def find_bridges(
        self,
        reference: RtgGraphLocalReference,
        status: str | None = "active",
    ) -> RtgGraphBridgeList:
        normalized_ref = _normalize_reference(reference, "reference")
        normalized_status = None if status is None else _validate_status(status)
        return RtgGraphBridgeList(
            bridges=tuple(
                _copy_assertion(assertion)
                for assertion in sorted(self._bridges.values(), key=lambda item: item.bridge_id)
                if (normalized_status is None or assertion.status == normalized_status)
                and (assertion.source == normalized_ref or assertion.target == normalized_ref)
            )
        )

    def revoke_bridge(
        self,
        bridge_id: str,
        *,
        revoked_at: str,
        revoked_by: str,
        reason: str,
    ) -> RtgGraphBridgeAssertion:
        assertion = self.get_bridge(bridge_id)
        revoked = RtgGraphBridgeAssertion(
            bridge_id=assertion.bridge_id,
            bridge_type=assertion.bridge_type,
            source=assertion.source,
            target=assertion.target,
            confidence=assertion.confidence,
            asserted_at=assertion.asserted_at,
            asserted_by=assertion.asserted_by,
            provenance=assertion.provenance,
            metadata=assertion.metadata,
            status="revoked",
            revoked_at=_validate_text(revoked_at, "revoked_at"),
            revoked_by=_validate_text(revoked_by, "revoked_by"),
            revocation_reason=_validate_text(reason, "reason"),
        )
        self._bridges[revoked.bridge_id] = revoked
        return _copy_assertion(revoked)

    def put_candidate(self, candidate: RtgGraphBridgeCandidateDraft) -> RtgGraphBridgeCandidate:
        normalized = _normalize_candidate_draft(candidate)
        candidate_id = _derive_candidate_id(normalized)
        stored = RtgGraphBridgeCandidate(
            candidate_id=candidate_id,
            bridge_type=normalized.bridge_type,
            source=normalized.source,
            target=normalized.target,
            confidence=normalized.confidence,
            proposed_at=normalized.proposed_at,
            proposed_by=normalized.proposed_by,
            evidence=normalized.evidence,
            rationale=normalized.rationale,
            metadata=normalized.metadata,
        )
        self._candidates[candidate_id] = stored
        return _copy_candidate(stored)

    def get_candidate(self, candidate_id: str) -> RtgGraphBridgeCandidate:
        return self._get_candidate(candidate_id)

    def list_candidates(self, status: str | None = "candidate_only") -> RtgGraphBridgeCandidateList:
        normalized_status = None if status is None else _validate_candidate_status(status)
        return RtgGraphBridgeCandidateList(
            candidates=tuple(
                _copy_candidate(candidate)
                for candidate in sorted(
                    self._candidates.values(), key=lambda item: item.candidate_id
                )
                if normalized_status is None or candidate.status == normalized_status
            )
        )

    def find_candidates(
        self,
        reference: RtgGraphLocalReference,
        status: str | None = "candidate_only",
    ) -> RtgGraphBridgeCandidateList:
        normalized_ref = _normalize_reference(reference, "reference")
        normalized_status = None if status is None else _validate_candidate_status(status)
        return RtgGraphBridgeCandidateList(
            candidates=tuple(
                _copy_candidate(candidate)
                for candidate in sorted(
                    self._candidates.values(), key=lambda item: item.candidate_id
                )
                if (normalized_status is None or candidate.status == normalized_status)
                and (candidate.source == normalized_ref or candidate.target == normalized_ref)
            )
        )

    def promote_candidate(
        self,
        candidate_id: str,
        *,
        asserted_at: str,
        asserted_by: str,
    ) -> RtgGraphBridgeAssertion:
        candidate = self._get_candidate(candidate_id)
        if candidate.status != "candidate_only":
            raise RtgGraphBridgeInvalid("only candidate_only candidates can be promoted")
        bridge = self.put_bridge(
            RtgGraphBridgeDraft(
                bridge_type=candidate.bridge_type,
                source=candidate.source,
                target=candidate.target,
                confidence=candidate.confidence,
                asserted_at=asserted_at,
                asserted_by=asserted_by,
                provenance=candidate.evidence,
                metadata={
                    **candidate.metadata,
                    "promoted_from_candidate_id": candidate.candidate_id,
                    "candidate_rationale": candidate.rationale,
                },
            )
        )
        promoted = RtgGraphBridgeCandidate(
            candidate_id=candidate.candidate_id,
            bridge_type=candidate.bridge_type,
            source=candidate.source,
            target=candidate.target,
            confidence=candidate.confidence,
            proposed_at=candidate.proposed_at,
            proposed_by=candidate.proposed_by,
            evidence=candidate.evidence,
            rationale=candidate.rationale,
            metadata=candidate.metadata,
            status="promoted",
            promoted_bridge_id=bridge.bridge_id,
        )
        self._candidates[promoted.candidate_id] = promoted
        return bridge

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        rejected_at: str,
        rejected_by: str,
        reason: str,
    ) -> RtgGraphBridgeCandidate:
        candidate = self._get_candidate(candidate_id)
        if candidate.status != "candidate_only":
            raise RtgGraphBridgeInvalid("only candidate_only candidates can be rejected")
        rejected = RtgGraphBridgeCandidate(
            candidate_id=candidate.candidate_id,
            bridge_type=candidate.bridge_type,
            source=candidate.source,
            target=candidate.target,
            confidence=candidate.confidence,
            proposed_at=candidate.proposed_at,
            proposed_by=candidate.proposed_by,
            evidence=candidate.evidence,
            rationale=candidate.rationale,
            metadata=candidate.metadata,
            status="rejected",
            rejected_at=_validate_text(rejected_at, "rejected_at"),
            rejected_by=_validate_text(rejected_by, "rejected_by"),
            rejection_reason=_validate_text(reason, "reason"),
        )
        self._candidates[rejected.candidate_id] = rejected
        return _copy_candidate(rejected)

    def _get_candidate(self, candidate_id: str) -> RtgGraphBridgeCandidate:
        normalized_id = _validate_candidate_id(candidate_id)
        try:
            candidate = self._candidates[normalized_id]
        except KeyError as error:
            raise RtgGraphBridgeNotFound(normalized_id) from error
        return _copy_candidate(candidate)


def _normalize_draft(bridge: RtgGraphBridgeDraft) -> RtgGraphBridgeDraft:
    source = _normalize_reference(bridge.source, "source")
    target = _normalize_reference(bridge.target, "target")
    if source.graph_id == target.graph_id:
        raise RtgGraphBridgeInvalid("bridge endpoints must be in different graphs")
    provenance = tuple(_normalize_reference(item, "provenance") for item in bridge.provenance)
    if not provenance:
        raise RtgGraphBridgeInvalid("provenance must contain at least one reference")
    return RtgGraphBridgeDraft(
        bridge_type=_validate_identifier(bridge.bridge_type, "bridge_type"),
        source=source,
        target=target,
        confidence=_validate_confidence(bridge.confidence),
        asserted_at=_validate_text(bridge.asserted_at, "asserted_at"),
        asserted_by=_validate_text(bridge.asserted_by, "asserted_by"),
        provenance=provenance,
        metadata=_validate_metadata(bridge.metadata),
    )


def _normalize_candidate_draft(
    candidate: RtgGraphBridgeCandidateDraft,
) -> RtgGraphBridgeCandidateDraft:
    source = _normalize_reference(candidate.source, "source")
    target = _normalize_reference(candidate.target, "target")
    if source.graph_id == target.graph_id:
        raise RtgGraphBridgeInvalid("candidate endpoints must be in different graphs")
    evidence = tuple(_normalize_reference(item, "evidence") for item in candidate.evidence)
    if not evidence:
        raise RtgGraphBridgeInvalid("evidence must contain at least one reference")
    return RtgGraphBridgeCandidateDraft(
        bridge_type=_validate_identifier(candidate.bridge_type, "bridge_type"),
        source=source,
        target=target,
        confidence=_validate_confidence(candidate.confidence),
        proposed_at=_validate_text(candidate.proposed_at, "proposed_at"),
        proposed_by=_validate_text(candidate.proposed_by, "proposed_by"),
        evidence=evidence,
        rationale=_validate_text(candidate.rationale, "rationale"),
        metadata=_validate_metadata(candidate.metadata),
    )


def _normalize_reference(
    reference: RtgGraphLocalReference,
    name: str,
) -> RtgGraphLocalReference:
    return RtgGraphLocalReference(
        graph_id=_validate_identifier(reference.graph_id, f"{name}.graph_id"),
        local_uuid=_validate_uuid(reference.local_uuid, f"{name}.local_uuid"),
    )


def _derive_bridge_id(bridge: RtgGraphBridgeDraft) -> str:
    identity = {
        "bridge_type": bridge.bridge_type,
        "source": _reference_identity(bridge.source),
        "target": _reference_identity(bridge.target),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"bridge_{digest}"


def _derive_candidate_id(candidate: RtgGraphBridgeCandidateDraft) -> str:
    identity = {
        "bridge_type": candidate.bridge_type,
        "source": _reference_identity(candidate.source),
        "target": _reference_identity(candidate.target),
        "evidence": [_reference_identity(item) for item in candidate.evidence],
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"candidate_{digest}"


def _reference_identity(reference: RtgGraphLocalReference) -> dict[str, str]:
    return {
        "graph_id": reference.graph_id,
        "local_uuid": str(reference.local_uuid),
    }


def _validate_bridge_id(value: str) -> str:
    text = _validate_text(value, "bridge_id")
    if not re.fullmatch(r"bridge_[a-f0-9]{20}", text):
        raise RtgGraphBridgeInvalid("bridge_id must be a derived bridge identifier")
    return text


def _validate_candidate_id(value: str) -> str:
    text = _validate_text(value, "candidate_id")
    if not re.fullmatch(r"candidate_[a-f0-9]{20}", text):
        raise RtgGraphBridgeInvalid("candidate_id must be a derived candidate identifier")
    return text


def _validate_identifier(value: str, name: str) -> str:
    text = _validate_text(value, name)
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", text):
        raise RtgGraphBridgeInvalid(f"{name} must be an identifier")
    return text


def _validate_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgGraphBridgeInvalid(f"{name} must be a non-empty string")
    return value.strip()


def _validate_uuid(value: UUID, name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise RtgGraphBridgeInvalid(f"{name} must be a UUID") from error


def _validate_confidence(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RtgGraphBridgeInvalid("confidence must be a number between 0 and 1")
    confidence = float(value)
    if not math.isfinite(confidence) or confidence < 0 or confidence > 1:
        raise RtgGraphBridgeInvalid("confidence must be a number between 0 and 1")
    return confidence


def _validate_status(value: str) -> str:
    status = _validate_text(value, "status")
    if status not in {"active", "revoked"}:
        raise RtgGraphBridgeInvalid("status must be active or revoked")
    return status


def _validate_candidate_status(value: str) -> str:
    status = _validate_text(value, "status")
    if status not in {"candidate_only", "promoted", "rejected"}:
        raise RtgGraphBridgeInvalid("status must be candidate_only, promoted, or rejected")
    return status


def _validate_metadata(value: JsonObject) -> JsonObject:
    metadata = copy.deepcopy(value)
    if not isinstance(metadata, dict):
        raise RtgGraphBridgeInvalid("metadata must be a JSON object")
    _validate_json_value(metadata)
    return metadata


def _validate_json_value(value: JsonValue) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RtgGraphBridgeInvalid("metadata keys must be strings")
            _validate_json_value(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise RtgGraphBridgeInvalid("metadata numbers must be finite")
    if value is None or isinstance(value, str | int | float | bool):
        return
    raise RtgGraphBridgeInvalid("metadata values must be JSON-serializable")


def _copy_assertion(assertion: RtgGraphBridgeAssertion) -> RtgGraphBridgeAssertion:
    return copy.deepcopy(assertion)


def _copy_candidate(candidate: RtgGraphBridgeCandidate) -> RtgGraphBridgeCandidate:
    return copy.deepcopy(candidate)
