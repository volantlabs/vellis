"""Governance of the one prospective definition set.

Realizes ``RTG::'Definition Delta Result'`` and the assessment behind
``RTGSystem::'Create or edit definition delta'``, ``'Review definition delta'``,
``'Activate definition delta'``, and ``'Discard definition delta'``, carrying
``VellisRequirements::nonDisruptiveDefinitionWork`` and
``VellisRequirements::definitionCardinality``.

There is one active set and at most one proposal, and the proposal is a working
document. It may be staged, re-staged, and left standing across other work while it
still carries findings — an owner drafting a vocabulary should not have to get it right
in one move. What the findings gate is activation, not staging.

Assessment answers all three questions at once: are the descriptions there, is the
proposal internally coherent, and would the graph the owner already has still conform
under it. The third is the one that catches a change that is fine in the abstract and
would invalidate real memory. None of this computes a diff against the active set: the
proposal is returned whole and the caller compares it with the focused views it can
already read.
"""

from __future__ import annotations

from dataclasses import dataclass

from vellis.canonical import DefinitionDelta
from vellis.definitions import GraphDefinitionSet, validate_definition_set
from vellis.graph import Graph
from vellis.outcomes import (
    OperationStatus,
    ValidationFinding,
    ValidationReport,
    ValidationScope,
)
from vellis.validation import assess_graph_conformance

__all__ = ["DefinitionDeltaResult", "SetDefinitionDeltaRequest", "assess_proposal"]


@dataclass(frozen=True, slots=True)
class SetDefinitionDeltaRequest:
    """What an owner offers as the next vocabulary.

    A named request rather than a bare definition set, because that is what the model
    declares the operation takes — and a request is the thing a later field would be
    added to.
    """

    proposed_definitions: GraphDefinitionSet


@dataclass(frozen=True, slots=True)
class DefinitionDeltaResult:
    """The sole proposal and its current assessment, or normal absence.

    An accepted result always identifies its evaluated revision. An assessment is
    present exactly when a proposal is, and shares that revision. A rejected or failed
    result carries no proposal, assessment, or revision at all — the caller retrieves
    the unchanged current proposal separately rather than reading one out of a refusal.
    """

    status: OperationStatus
    summary: str
    findings: tuple[ValidationFinding, ...] = ()
    definition_delta: DefinitionDelta | None = None
    assessment: ValidationReport | None = None
    evaluated_revision: int | None = None
    resulting_revision: int | None = None

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED


def assess_proposal(
    proposed: GraphDefinitionSet, graph: Graph, evaluated_revision: int
) -> ValidationReport:
    """Assess a proposal's descriptions, internal consistency, and graph impact.

    The graph is assessed against the proposal rather than against the active set, which
    is what turns "this vocabulary is coherent" into "this vocabulary still fits the
    memory the owner has".
    """
    findings = (
        *validate_definition_set(proposed, require_descriptions=True),
        *assess_graph_conformance(graph, proposed),
    )
    return ValidationReport(
        scope=ValidationScope.DEFINITION_DELTA,
        conforms=not findings,
        evaluated_revision=evaluated_revision,
        findings=findings,
    )
