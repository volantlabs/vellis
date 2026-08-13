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

from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    LinkEnd,
    LinkTypeDefinition,
    RelationshipConstraint,
    relationship_identity,
)
from vellis.outcomes import (
    OperationStatus,
    ValidationFinding,
    ValidationReport,
)

__all__ = [
    "ActivateDefinitionDeltaRequest",
    "DefinitionChange",
    "DefinitionDeltaResult",
    "DirectAssociationMultiplicitySelection",
    "LinkMultiplicitySelection",
    "SetDefinitionDeltaRequest",
    "definition_change_findings",
]


@dataclass(frozen=True, slots=True)
class LinkMultiplicitySelection:
    link_type_key: str
    constrained_end: LinkEnd
    constrained_endpoint_type_keys: tuple[str, ...]
    opposite_endpoint_type_keys: tuple[str, ...]

    def identity(self) -> tuple[object, ...]:
        return (
            "linkMultiplicity",
            self.link_type_key,
            self.constrained_end,
            frozenset(self.constrained_endpoint_type_keys),
            frozenset(self.opposite_endpoint_type_keys),
        )


@dataclass(frozen=True, slots=True)
class DirectAssociationMultiplicitySelection:
    constrained_end: DirectAssociationEnd
    anchor_type_keys: tuple[str, ...]
    associated_data_type_keys: tuple[str, ...]

    def identity(self) -> tuple[object, ...]:
        return (
            "directAssociationMultiplicity",
            self.constrained_end,
            frozenset(self.anchor_type_keys),
            frozenset(self.associated_data_type_keys),
        )


@dataclass(frozen=True, slots=True)
class DefinitionChange:
    """One bounded natural-keyed edit of proposed definition meaning."""

    anchor_type_upserts: tuple[AnchorTypeDefinition, ...] = ()
    associated_data_type_upserts: tuple[AssociatedDataTypeDefinition, ...] = ()
    link_type_upserts: tuple[LinkTypeDefinition, ...] = ()
    relationship_constraint_upserts: tuple[RelationshipConstraint, ...] = ()
    type_removals: tuple[str, ...] = ()
    link_multiplicity_removals: tuple[LinkMultiplicitySelection, ...] = ()
    direct_association_multiplicity_removals: tuple[
        DirectAssociationMultiplicitySelection, ...
    ] = ()


def definition_change_findings(change: DefinitionChange) -> tuple[ValidationFinding, ...]:
    """Return duplicate and upsert/removal conflicts in one keyed edit."""
    findings: list[ValidationFinding] = []
    type_commands = [
        *(each.type_key for each in change.anchor_type_upserts),
        *(each.type_key for each in change.associated_data_type_upserts),
        *(each.type_key for each in change.link_type_upserts),
        *change.type_removals,
    ]
    seen: set[str] = set()
    for key in type_commands:
        if key in seen:
            findings.append(
                ValidationFinding(
                    summary=f"type key {key!r} has more than one command in the edit",
                    implicated_definitions=(f"type:{key}",),
                )
            )
        seen.add(key)
    relationship_commands = [
        *(relationship_identity(each) for each in change.relationship_constraint_upserts),
        *(each.identity() for each in change.link_multiplicity_removals),
        *(each.identity() for each in change.direct_association_multiplicity_removals),
    ]
    seen_relationships: set[tuple[object, ...]] = set()
    for identity in relationship_commands:
        if identity in seen_relationships:
            findings.append(
                ValidationFinding(summary="a multiplicity natural identity has multiple commands")
            )
        seen_relationships.add(identity)
    return tuple(findings)


@dataclass(frozen=True, slots=True)
class SetDefinitionDeltaRequest:
    """One bounded keyed edit of the sole proposed vocabulary."""

    change: DefinitionChange


@dataclass(frozen=True, slots=True)
class ActivateDefinitionDeltaRequest:
    assessment_id: str


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
    proposed_definition_identity: str | None = None
    graph_overlay_identity: str | None = None
    staged_anchor_count: int | None = None
    staged_associated_data_count: int | None = None
    staged_link_count: int | None = None
    staged_removal_count: int | None = None
    assessment: ValidationReport | None = None
    evaluated_revision: int | None = None
    resulting_revision: int | None = None

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED
