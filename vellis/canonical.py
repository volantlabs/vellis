"""Canonical transition meaning and proposal equality.

Realizes ``RTG::'Canonical State'``, ``RTG::Provenance``, ``RTG::'Definition Delta'``,
``RTG::'History Record'``, ``RTG::'Canonical Record'``, ``RTG::'Initial State Record'``,
together with ``VellisRequirements::durableCanonicalHistory`` as far as one initial
base carries it.

``RTG::'Canonical Change'``, ``RTG::'Transition Kind'``,
``RTG::'Definition Delta Disposition'``, and ``RTG::'Canonical Transition Record'``.

``RTG::'State Change Ledger'`` is realized by the durable store, not by a second
in-memory collection: one authority for replay, not two that can drift.

A transition carries the semantic change itself, not a picture of the result. That is
what makes replay possible without activity history, and it is why an ordinary graph
mutation carries its accepted graph change while only a historical restoration may carry
a complete replacement graph. Each kind may touch only its own facets, and
:func:`transition_findings` is where that rule lives, so a record that could not be
replayed cannot be written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from vellis.changes import GraphChange
from vellis.outcomes import ValidationFinding

__all__ = [
    "CanonicalChange",
    "CanonicalTransitionRecord",
    "DefinitionDeltaDisposition",
    "Provenance",
    "TransitionKind",
    "now",
    "transition_findings",
]


class TransitionKind(Enum):
    """What a canonical transition is."""

    GRAPH_MUTATION = "graphMutation"
    DEFINITION_DELTA_CHANGE = "definitionDeltaChange"
    DEFINITION_ACTIVATION = "definitionActivation"
    HISTORICAL_RESTORATION = "historicalRestoration"


class DefinitionDeltaDisposition(Enum):
    """What a transition does to the sole definition delta.

    ``UNCHANGED`` is distinct from ``ABSENT``: one says the transition did not touch the
    delta, the other says it removed it.
    """

    UNCHANGED = "unchanged"
    PRESENT = "present"
    ABSENT = "absent"


def now() -> datetime:
    """Return the current recorded time as an aware UTC instant."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Provenance:
    """Identifies who initiated a record and, when applicable, its bounded source."""

    initiator: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalChange:
    """Replay-sufficient meaning for one transition.

    An absent graph form or active-definition value means unchanged. The two graph forms
    are never both present.
    """

    delta_disposition: DefinitionDeltaDisposition = DefinitionDeltaDisposition.UNCHANGED
    graph_change: GraphChange | None = None


@dataclass(frozen=True, slots=True)
class CanonicalTransitionRecord:
    """Establishes one contiguous canonical transition."""

    prior_revision: int
    resulting_revision: int
    kind: TransitionKind
    change: CanonicalChange
    provenance: Provenance
    recorded_at: datetime = field(default_factory=now)

    @property
    def established_revision(self) -> int:
        return self.resulting_revision


def transition_findings(record: CanonicalTransitionRecord) -> tuple[ValidationFinding, ...]:
    """Return why this transition could not be replayed for its kind, if it could not."""
    findings: list[ValidationFinding] = []
    change = record.change
    kind = record.kind
    label = f"transition {record.prior_revision}->{record.resulting_revision}"

    def refuse(reason: str) -> None:
        findings.append(ValidationFinding(summary=f"{label} {reason}"))

    if record.resulting_revision != record.prior_revision + 1:
        refuse("does not advance the revision by exactly one")
    if kind is TransitionKind.GRAPH_MUTATION:
        if change.graph_change is None:
            refuse("is a graph mutation but carries no graph change")
        if change.delta_disposition is not DefinitionDeltaDisposition.UNCHANGED:
            refuse("is a graph mutation but changes the definition delta")
    elif kind is TransitionKind.DEFINITION_DELTA_CHANGE:
        if change.graph_change is not None:
            refuse("is a definition-delta change but changes the graph")
        if change.delta_disposition is not DefinitionDeltaDisposition.ABSENT:
            refuse("is a definition-delta discard but does not clear the delta")
    else:
        refuse("uses the bounded transition carrier for a SQLite-native operation")
    return tuple(findings)
