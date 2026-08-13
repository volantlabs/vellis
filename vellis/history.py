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

from dataclasses import dataclass
from datetime import datetime

from vellis.outcomes import ValidationFinding

__all__ = [
    "MAXIMUM_REVISION",
    "HistoricalSelection",
    "RevisionSelection",
    "TimeSelection",
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

# The largest revision a ledger can bind, which is what the store can hold in one column.
MAXIMUM_REVISION = 2**63 - 1


def selection_findings(selection: HistoricalSelection) -> tuple[ValidationFinding, ...]:
    """Return every reason a selector cannot be resolved before the ledger is consulted."""
    if isinstance(selection, RevisionSelection) and not (
        0 <= selection.revision <= MAXIMUM_REVISION
    ):
        # Bounded rather than merely non-negative: a number no ledger could hold is an
        # unknown revision, and asking the store about it would fail on the way in rather
        # than answer.
        return (
            ValidationFinding(
                summary=f"a revision selector names a committed revision, not {selection.revision}"
            ),
        )
    if isinstance(selection, TimeSelection) and selection.time.tzinfo is None:
        return (ValidationFinding(summary="a time selector must say which zone it is in"),)
    return ()
