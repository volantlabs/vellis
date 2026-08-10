"""Canonical state, its owned history base, and canonical-state equality.

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

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from vellis.changes import GraphChange, apply_change
from vellis.definitions import GraphDefinitionSet, definition_set_equal
from vellis.graph import Graph, graph_equal
from vellis.outcomes import ValidationFinding

__all__ = [
    "CanonicalChange",
    "CanonicalRecord",
    "CanonicalState",
    "CanonicalTransitionRecord",
    "DefinitionDelta",
    "DefinitionDeltaDisposition",
    "InitialStateRecord",
    "Provenance",
    "TransitionKind",
    "ReplayError",
    "canonical_state_equal",
    "definition_delta_equal",
    "now",
    "replay",
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
class DefinitionDelta:
    """The sole prospective next definition set."""

    proposed_definitions: GraphDefinitionSet


def definition_delta_equal(left: DefinitionDelta | None, right: DefinitionDelta | None) -> bool:
    """Compare delta presence and, when present, proposed-definition content."""
    if left is None or right is None:
        return left is None and right is None
    return definition_set_equal(left.proposed_definitions, right.proposed_definitions)


@dataclass(frozen=True, slots=True)
class CanonicalState:
    """One canonical-state tuple at an established revision."""

    graph: Graph
    active_definitions: GraphDefinitionSet
    revision: int
    definition_delta: DefinitionDelta | None = None


def canonical_state_equal(left: CanonicalState, right: CanonicalState) -> bool:
    """Compare two canonical states by canonical semantic equality.

    Revision, graph, active definitions, and delta presence must agree, and a present
    delta's proposed set must be semantically equal.
    """
    return (
        left.revision == right.revision
        and graph_equal(left.graph, right.graph)
        and definition_set_equal(left.active_definitions, right.active_definitions)
        and definition_delta_equal(left.definition_delta, right.definition_delta)
    )


@dataclass(frozen=True, slots=True)
class InitialStateRecord:
    """Establishes the ledger's owned history base.

    Its revision may exceed zero when a fresh RTG is seeded from reconstructed
    snapshot state; the record then makes no claim about transitions before that base.
    """

    canonical_state: CanonicalState
    initialization_summary: str
    provenance: Provenance
    recorded_at: datetime = field(default_factory=now)

    @property
    def established_revision(self) -> int:
        return self.canonical_state.revision


@dataclass(frozen=True, slots=True)
class CanonicalChange:
    """Replay-sufficient meaning for one transition.

    An absent graph form or active-definition value means unchanged. The two graph forms
    are never both present.
    """

    delta_disposition: DefinitionDeltaDisposition = DefinitionDeltaDisposition.UNCHANGED
    graph_change: GraphChange | None = None
    replacement_graph: Graph | None = None
    active_definitions: GraphDefinitionSet | None = None
    definition_delta: DefinitionDelta | None = None


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


type CanonicalRecord = InitialStateRecord | CanonicalTransitionRecord


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
    if change.graph_change is not None and change.replacement_graph is not None:
        refuse("carries both a graph change and a replacement graph")
    if (change.delta_disposition is DefinitionDeltaDisposition.PRESENT) != (
        change.definition_delta is not None
    ):
        refuse("has a delta disposition that disagrees with whether it carries a delta")

    if kind is TransitionKind.GRAPH_MUTATION:
        if change.graph_change is None:
            refuse("is a graph mutation but carries no graph change")
        if change.replacement_graph is not None:
            refuse("is a graph mutation but carries a complete replacement graph")
        if change.active_definitions is not None:
            refuse("is a graph mutation but changes active definitions")
        if change.delta_disposition is not DefinitionDeltaDisposition.UNCHANGED:
            refuse("is a graph mutation but changes the definition delta")
    elif kind is TransitionKind.DEFINITION_DELTA_CHANGE:
        if change.graph_change is not None or change.replacement_graph is not None:
            refuse("is a definition-delta change but changes the graph")
        if change.active_definitions is not None:
            refuse("is a definition-delta change but changes active definitions")
        if change.delta_disposition is DefinitionDeltaDisposition.UNCHANGED:
            refuse("is a definition-delta change but leaves the delta unchanged")
    elif kind is TransitionKind.DEFINITION_ACTIVATION:
        if change.graph_change is not None or change.replacement_graph is not None:
            refuse("is an activation but changes the graph")
        if change.active_definitions is None:
            refuse("is an activation but supplies no active definitions")
        if change.delta_disposition is not DefinitionDeltaDisposition.ABSENT:
            refuse("is an activation but does not clear the delta")
    else:
        if change.replacement_graph is None:
            refuse("is a restoration but carries no replacement graph")
        if change.graph_change is not None:
            refuse("is a restoration but carries a graph change")
        if change.active_definitions is None:
            refuse("is a restoration but supplies no active definitions")
        if change.delta_disposition is not DefinitionDeltaDisposition.ABSENT:
            refuse("is a restoration but does not clear the delta")
    return tuple(findings)


def replay(
    initial: InitialStateRecord, transitions: Sequence[CanonicalTransitionRecord]
) -> CanonicalState:
    """Reconstruct canonical state by replaying through the final canonical record.

    Replay applies the same change the commit applied, which is what "replay-sufficient"
    has to mean if the ledger is to be authority rather than a log beside one.
    """
    state = initial.canonical_state
    for record in transitions:
        if record.prior_revision != state.revision:
            raise ReplayError(
                f"transition follows revision {record.prior_revision} but replay is at "
                f"{state.revision}"
            )
        findings = transition_findings(record)
        if findings:
            raise ReplayError(findings[0].summary)
        state = _advance(state, record)
    return state


def _advance(state: CanonicalState, record: CanonicalTransitionRecord) -> CanonicalState:
    change = record.change
    graph = state.graph
    if change.graph_change is not None:
        graph = apply_change(graph, change.graph_change)
    elif change.replacement_graph is not None:
        graph = change.replacement_graph
    delta = state.definition_delta
    if change.delta_disposition is DefinitionDeltaDisposition.ABSENT:
        delta = None
    elif change.delta_disposition is DefinitionDeltaDisposition.PRESENT:
        delta = change.definition_delta
    return CanonicalState(
        graph=graph,
        active_definitions=(
            state.active_definitions
            if change.active_definitions is None
            else change.active_definitions
        ),
        revision=record.resulting_revision,
        definition_delta=delta,
    )


class ReplayError(ValueError):
    """Raised when a ledger cannot be replayed as written."""
