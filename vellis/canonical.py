"""Canonical state, its owned history base, and canonical-state equality.

Realizes ``RTG::'Canonical State'``, ``RTG::Provenance``, ``RTG::'Definition Delta'``,
``RTG::'History Record'``, ``RTG::'Canonical Record'``, ``RTG::'Initial State Record'``,
together with ``VellisRequirements::durableCanonicalHistory`` as far as one initial
base carries it.

``RTG::'State Change Ledger'`` is realized by the durable store, not by a second
in-memory collection: one authority for replay, not two that can drift. Transition
records carry a replay-sufficient ``RTG::'Canonical Change'`` whose graph form is the
accepted graph change; that change is authored by the slice that first commits one, so
this slice establishes only the owned base and the current-state projection that replay
through the final canonical record produces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from vellis.definitions import GraphDefinitionSet, definition_set_equal
from vellis.graph import Graph, graph_equal

__all__ = [
    "CanonicalState",
    "DefinitionDelta",
    "InitialStateRecord",
    "Provenance",
    "canonical_state_equal",
    "definition_delta_equal",
    "now",
]


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
