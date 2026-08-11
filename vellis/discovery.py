"""What a cold agent reads before it can say anything about a graph.

Realizes ``RTG::'Anchor Type Summary'``, ``RTG::'Definition Inspection Request'``,
``RTG::'Anchor Definition Detail'``, ``RTG::'Definition Summary Result'``,
``RTG::'Definition Inspection Result'``, ``RTGSystem::'Discover evaluated graph
definitions'``, and the current-state half of
``VellisRequirements::agentDefinitionDiscoverability``.

Discovery is two reads, shallow then focused, and the split is the point: an agent that
knows nothing asks once for the whole anchor vocabulary, then asks again only about the
anchors it actually needs. Each result carries the revision it was evaluated at, so an
agent that reads a summary and then an inspection can tell whether the definitions moved
underneath it — that comparison is the whole mechanism, and it needs no session or lock.

A neighborhood is complete for its anchor and contains nothing else. Completeness is
what an agent needs in order to compose a conforming change for that anchor without
asking again: the associated-data types that may ground it, the link types it or those
data types may participate in, the associated-data types sitting at the far end of those
links — otherwise the agent is handed a link it cannot fill in — and the multiplicity
rules that actually govern it. Property and endpoint rules ride along inside the type
definitions that own them, because that is where they live.

"Governs it" follows how each rule is actually quantified, because that is what decides
whether the rule will reject the agent's change. A rule counted at the anchor end runs
over anchors of its named types, so it belongs only when this anchor is one of them — a
rule about some other anchor's notes says nothing about this one, even though both carry
notes. The same rule counted at the data end runs over every data object of its named
types, so it belongs whenever this anchor grounds one of them, whichever anchor the rule
names. A link multiplicity rule belongs when the anchor or one of its grounding data
types participates, whether or not the link type itself lists that type as a permitted
endpoint.

The result is closed: whatever definition an included rule names — its link type, its
associated-data types — is included too. A rule the agent can read but whose subject it
cannot resolve is worse than no rule at all, because the change gets refused by a bound
it can see and cannot understand.

Historical selection is part of the same request in the model. It arrives with the slice
that can resolve a revision; until then a request selects current state, and nothing
here pretends otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    GraphDefinitionSet,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    RelationshipConstraint,
)
from vellis.history import HistoricalSelection
from vellis.outcomes import OperationStatus, ValidationFinding

__all__ = [
    "AnchorDefinitionDetail",
    "AnchorTypeSummary",
    "DefinitionInspectionRequest",
    "DefinitionInspectionResult",
    "DefinitionSummaryResult",
    "anchor_neighborhood",
    "inspection_findings",
    "summarize_anchor_types",
]


@dataclass(frozen=True, slots=True)
class AnchorTypeSummary:
    """Projects one anchor type's key and description.

    The definition itself stays the authority; this is what a shallow read shows.
    """

    type_key: str
    description: str | None


@dataclass(frozen=True, slots=True)
class DefinitionSummaryResult:
    """The complete shallow anchor vocabulary at one evaluated state.

    Evaluated revision and delta presence are present exactly for an accepted result: a
    summary that could not be returned completely returns no vocabulary and no
    current-state metadata either, so a caller can never mistake a partial answer for a
    whole one.
    """

    status: OperationStatus
    summary: str
    findings: tuple[ValidationFinding, ...] = ()
    anchor_types: tuple[AnchorTypeSummary, ...] = ()
    evaluated_revision: int | None = None
    delta_present: bool | None = None

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED


@dataclass(frozen=True, slots=True)
class DefinitionInspectionRequest:
    """A non-empty unique selection of anchor type keys, at one evaluated state.

    The selector rides inside the request because the model puts it there: an inspection
    is one question about one state, not a question plus a separate context.
    """

    anchor_type_keys: tuple[str, ...]
    historical_selection: HistoricalSelection | None = None


@dataclass(frozen=True, slots=True)
class AnchorDefinitionDetail:
    """One complete active-definition neighborhood for one selected anchor."""

    anchor_type: AnchorTypeDefinition
    associated_data_types: tuple[AssociatedDataTypeDefinition, ...] = ()
    link_types: tuple[LinkTypeDefinition, ...] = ()
    relationship_constraints: tuple[RelationshipConstraint, ...] = ()


@dataclass(frozen=True, slots=True)
class DefinitionInspectionResult:
    """Complete neighborhoods for every requested anchor, or none at all."""

    status: OperationStatus
    summary: str
    request: DefinitionInspectionRequest
    findings: tuple[ValidationFinding, ...] = ()
    anchor_details: tuple[AnchorDefinitionDetail, ...] = ()
    evaluated_revision: int | None = None

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED


def summarize_anchor_types(definitions: GraphDefinitionSet) -> tuple[AnchorTypeSummary, ...]:
    """Return every active anchor type exactly once."""
    return tuple(
        AnchorTypeSummary(type_key=each.type_key, description=each.description)
        for each in definitions.anchor_types
    )


def inspection_findings(
    request: DefinitionInspectionRequest, definitions: GraphDefinitionSet
) -> tuple[ValidationFinding, ...]:
    """Return why this selection cannot be answered completely, if it cannot."""
    findings: list[ValidationFinding] = []
    if not request.anchor_type_keys:
        findings.append(
            ValidationFinding(
                summary="the selection names no anchor type; at least one is required"
            )
        )
    seen: set[str] = set()
    for type_key in request.anchor_type_keys:
        label = f"anchorType:{type_key}"
        if type_key in seen:
            findings.append(
                ValidationFinding(
                    summary=f"the selection names {type_key!r} more than once",
                    implicated_definitions=(label,),
                )
            )
            continue
        seen.add(type_key)
        if definitions.anchor_type(type_key) is None:
            findings.append(
                ValidationFinding(
                    summary=f"{type_key!r} is not an active anchor type",
                    implicated_definitions=(label,),
                )
            )
    return tuple(findings)


def anchor_neighborhood(type_key: str, definitions: GraphDefinitionSet) -> AnchorDefinitionDetail:
    """Return everything active that bears on one anchor type, and nothing else."""
    anchor_type = definitions.anchor_type(type_key)
    assert anchor_type is not None

    grounding_keys = {
        each.type_key
        for each in definitions.associated_data_types
        if type_key in each.permitted_anchor_type_keys
    }
    neighborhood_keys = {type_key, *grounding_keys}

    constraints = tuple(
        each
        for each in definitions.relationship_constraints
        if _constrains(each, type_key, grounding_keys, neighborhood_keys)
    )

    link_keys = {
        each.type_key for each in definitions.link_types if neighborhood_keys & _endpoint_keys(each)
    }
    link_keys |= {
        each.link_type_key for each in constraints if isinstance(each, LinkMultiplicityConstraint)
    }
    link_types = tuple(each for each in definitions.link_types if each.type_key in link_keys)

    # Close over what the neighborhood already names: the far end of every included link
    # type, and every data type an included rule is about.
    data_keys = set(grounding_keys)
    data_keys |= {key for each in link_types for key in _endpoint_keys(each)}
    for constraint in constraints:
        if isinstance(constraint, LinkMultiplicityConstraint):
            data_keys |= frozenset(constraint.constrained_endpoint_type_keys)
            data_keys |= frozenset(constraint.opposite_endpoint_type_keys)
        else:
            data_keys |= frozenset(constraint.associated_data_type_keys)
    data_types = tuple(
        each for each in definitions.associated_data_types if each.type_key in data_keys
    )

    return AnchorDefinitionDetail(
        anchor_type=anchor_type,
        associated_data_types=data_types,
        link_types=link_types,
        relationship_constraints=constraints,
    )


def _endpoint_keys(link_type: LinkTypeDefinition) -> frozenset[str]:
    constraint = link_type.endpoint_constraint
    return frozenset(constraint.permitted_source_type_keys) | frozenset(
        constraint.permitted_target_type_keys
    )


def _constrains(
    constraint: RelationshipConstraint,
    type_key: str,
    grounding_keys: set[str],
    neighborhood_keys: set[str],
) -> bool:
    if isinstance(constraint, LinkMultiplicityConstraint):
        participants = frozenset(constraint.constrained_endpoint_type_keys) | frozenset(
            constraint.opposite_endpoint_type_keys
        )
        return bool(participants & neighborhood_keys)
    assert isinstance(constraint, DirectAssociationMultiplicityConstraint)
    if type_key in constraint.anchor_type_keys:
        return True
    # Counted at the data end, the rule runs over every object of its data types, so it
    # binds this anchor's data objects even when it names a different anchor.
    return constraint.constrained_end is DirectAssociationEnd.ASSOCIATED_DATA and bool(
        frozenset(constraint.associated_data_type_keys) & grounding_keys
    )
