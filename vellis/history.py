"""Reading the graph and its vocabulary as they were.

Realizes ``RTG::'Historical State Selection'`` and its two specializations, and the
historical half of ``RTGSystem::'Discover evaluated graph definitions'`` and
``'Query graph'``, carrying ``VellisRequirements::historicalStateCorrectness`` and the
selection half of ``VellisRequirements::boundedHistoricalSelectionWork``.

A selector names a revision or a time, never both, and a time means the greatest revision
committed at or before it — so "what did I know on Tuesday" has one answer even though
nothing happened on Tuesday. Everything else about a historical read is the current read:
the same query meaning, the same bounds, the same shaping. That is the point. A caller
that has learned to ask a question can ask it of any committed state.

The two reads cost different things, and the model says so. A vocabulary is rebuilt from
the records that changed vocabulary, skipping the graph work in between. A graph has to
be replayed, because a graph is what the transitions are about.

An unresolvable selector returns findings and nothing else — no partial content, no
evaluated revision. Reporting the revision a caller did not reach would invite them to
use it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from vellis.canonical import (
    CanonicalState,
    CanonicalTransitionRecord,
    DefinitionDelta,
    DefinitionDeltaDisposition,
)
from vellis.definitions import GraphDefinitionSet
from vellis.outcomes import ValidationFinding

__all__ = [
    "EvaluatedDefinitions",
    "HistoricalSelection",
    "RevisionSelection",
    "TimeSelection",
    "definitions_through",
    "selection_findings",
]


@dataclass(frozen=True, slots=True)
class RevisionSelection:
    """Selects one committed revision directly."""

    revision: int


@dataclass(frozen=True, slots=True)
class TimeSelection:
    """Selects the greatest revision committed at or before one instant."""

    time: datetime


HistoricalSelection = RevisionSelection | TimeSelection


@dataclass(frozen=True, slots=True)
class EvaluatedDefinitions:
    """The vocabulary in force at one revision, and whether a proposal stood then."""

    active_definitions: GraphDefinitionSet
    delta_present: bool


def selection_findings(selection: HistoricalSelection) -> tuple[ValidationFinding, ...]:
    """Return every reason a selector cannot be resolved before the ledger is consulted."""
    if isinstance(selection, RevisionSelection) and selection.revision < 0:
        return (
            ValidationFinding(
                summary=f"a revision selector names a committed revision, not {selection.revision}"
            ),
        )
    if isinstance(selection, TimeSelection) and selection.time.tzinfo is None:
        return (ValidationFinding(summary="a time selector must say which zone it is in"),)
    return ()


def definitions_through(
    base: CanonicalState, transitions: Sequence[CanonicalTransitionRecord]
) -> EvaluatedDefinitions:
    """Rebuild the vocabulary from definition-changing records alone.

    ``transitions`` carries only the records that touched definitions, so this walks what
    changed the answer rather than everything that happened. Delta presence is part of the
    answer: an agent reading a historical summary needs to know a proposal stood then,
    even though it can only retrieve the current one.
    """
    active = base.active_definitions
    delta: DefinitionDelta | None = base.definition_delta
    for record in transitions:
        change = record.change
        if change.active_definitions is not None:
            active = change.active_definitions
        if change.delta_disposition is DefinitionDeltaDisposition.PRESENT:
            delta = change.definition_delta
        elif change.delta_disposition is DefinitionDeltaDisposition.ABSENT:
            delta = None
    return EvaluatedDefinitions(active_definitions=active, delta_present=delta is not None)
