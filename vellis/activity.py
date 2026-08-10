"""Observational history, and the bounded reads over both ledgers.

Realizes ``RTG::'Activity Record'``, ``RTG::'Activity Ledger'``, ``RTG::'History Query'``,
``RTG::'History Entry'`` and its two specializations, and ``RTG::'History Result'``,
together with ``RTGSystem::'Inspect state-change history'``,
``RTGSystem::'Inspect activity history'``, and ``RTGSystem::'Manage activity retention'``,
carrying ``VellisRequirements::dualLedgerSeparation`` and
``VellisRequirements::boundedHistoryRead``.

Two ledgers, and the separation is the whole point. The canonical ledger is authority:
replay reads it and it establishes state. The activity ledger is a record of what was
asked and what happened, and nothing reads it to decide anything. That asymmetry is why
the owner can delete activity history without touching what their memory *is* — and why
an activity summary carries a bounded description rather than the rows it returned.

An activity read selects before its own record is appended. Otherwise every read would
observe itself, and the ledger would answer a slightly different question each time it
was asked the same one.

The bound works as it does for a query: a result larger than the caller asked for is
refused whole. An owner reviewing their history needs to know they saw all of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from vellis.canonical import Provenance, TransitionKind
from vellis.outcomes import OperationStatus, ValidationFinding

__all__ = [
    "ActivityHistoryEntry",
    "ActivityRecord",
    "CanonicalHistoryEntry",
    "HistoryKind",
    "HistoryQuery",
    "HistoryResult",
    "RetentionDecision",
    "history_query_findings",
    "retention_findings",
]


class HistoryKind(Enum):
    """Which ledger a history read selects. A result never mixes the two."""

    CANONICAL = "canonical"
    ACTIVITY = "activity"


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    """One bounded owner-facing observation of a determined outcome.

    ``semantic_scope`` says what the operation was about — a capability's subject, not
    its answer. Nothing here may carry result rows, canonical payloads, or a guess at
    why the caller asked.
    """

    capability: str
    outcome_category: OperationStatus
    semantic_scope: str
    summary: str
    provenance: Provenance
    recorded_at: datetime
    evaluated_revision: int | None = None


@dataclass(frozen=True, slots=True)
class HistoryQuery:
    """One bounded read of one ledger over an optional inclusive interval."""

    kind: HistoryKind
    maximum_records: int
    start_time: datetime | None = None
    end_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class CanonicalHistoryEntry:
    """An owner-facing projection of one canonical record.

    An initial record has neither a prior revision nor a transition kind; a transition
    has both. The replay-sufficient change is deliberately absent: this is for review,
    not authority, and copying the payload here would make it a second one.
    """

    recorded_at: datetime
    provenance: Provenance
    summary: str
    revision: int
    prior_revision: int | None = None
    transition_kind: TransitionKind | None = None


@dataclass(frozen=True, slots=True)
class ActivityHistoryEntry:
    """An owner-facing projection of one activity record."""

    recorded_at: datetime
    provenance: Provenance
    summary: str
    capability: str
    outcome_category: OperationStatus
    semantic_scope: str
    evaluated_revision: int | None = None


@dataclass(frozen=True, slots=True)
class HistoryResult:
    """The outcome of one history read.

    Exactly one entry family is ever populated, and a refusal populates neither.
    """

    status: OperationStatus
    summary: str
    query: HistoryQuery
    findings: tuple[ValidationFinding, ...] = ()
    evaluated_revision: int | None = None
    canonical_entries: tuple[CanonicalHistoryEntry, ...] = ()
    activity_entries: tuple[ActivityHistoryEntry, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED


@dataclass(frozen=True, slots=True)
class RetentionDecision:
    """An owner's decision about which observational records to keep.

    Records recorded before ``remove_before`` are removed. The owner names a boundary
    rather than individual records, because the thing being forgotten is a stretch of
    their own history, not a row.
    """

    remove_before: datetime


def retention_findings(decision: RetentionDecision) -> tuple[ValidationFinding, ...]:
    """Return every reason ``decision`` cannot be applied.

    Beside the read's own bound check rather than in the store, so the same defect is
    the same kind of answer: a boundary the caller can correct is a refusal, not a
    report that the store broke.
    """
    if decision.remove_before.tzinfo is None:
        return (
            ValidationFinding(summary="the retention boundary does not say which zone it is in"),
        )
    return ()


def history_query_findings(query: HistoryQuery) -> tuple[ValidationFinding, ...]:
    """Return every reason ``query`` cannot be answered."""
    findings: list[ValidationFinding] = []
    if query.maximum_records < 1:
        findings.append(
            ValidationFinding(
                summary=f"maximum records must be positive, not {query.maximum_records}"
            )
        )
    # A bound with no zone cannot be ordered against a stored instant. Reporting that is
    # the difference between an answer the caller can trust and one that quietly means a
    # different interval on each ledger.
    for label, bound in (("start", query.start_time), ("end", query.end_time)):
        if bound is not None and bound.tzinfo is None:
            findings.append(
                ValidationFinding(summary=f"the {label} bound does not say which zone it is in")
            )
    if (
        query.start_time is not None
        and query.end_time is not None
        and query.start_time.tzinfo is not None
        and query.end_time.tzinfo is not None
        and query.start_time > query.end_time
    ):
        findings.append(
            ValidationFinding(summary="the interval starts after it ends, so it selects nothing")
        )
    return tuple(findings)
