"""Pure, bounded derivation of exact multiplicity impact reasons.

The caller supplies only changed endpoint identities, changed or incident relationship
objects, and their lookup endpoints.  This module owns no graph state and never expands
an incident neighborhood.  It turns those already-bounded old/proposed facts into the
exact rule-subject-end reasons whose counts can differ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vellis.definitions import (
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    LinkEnd,
    LinkMultiplicityConstraint,
    RelationshipConstraint,
    relationship_identity,
)
from vellis.graph import Anchor, AssociatedDataObject, GraphObject, Link
from vellis.normalized import semantic_identity

ReasonKind = Literal[
    "relationshipMembershipChanged",
    "subjectMembershipChanged",
    "oppositeMembershipChanged",
    "ruleMeaningChanged",
]


@dataclass(frozen=True, slots=True, order=True)
class MultiplicityImpactReason:
    """One exact reason a rule's count for one constrained subject can differ."""

    rule_key: str
    subject_uuid: str
    constrained_end: str
    reason_kind: ReasonKind


@dataclass(frozen=True, slots=True)
class ImpactNeighborhood:
    """Already-bounded old and proposed relationship facts plus lookup identities."""

    old_objects: dict[str, GraphObject]
    proposed_objects: dict[str, GraphObject]
    examined_relationship_uuids: frozenset[str]
    changed_relationship_uuids: frozenset[str]
    changed_participant_uuids: frozenset[str]


@dataclass(frozen=True, slots=True)
class IndexedMultiplicityFacts:
    """One type-indexed view reused across every exact rule evaluation."""

    objects: dict[str, GraphObject]
    participants_by_type: dict[str, frozenset[str]]
    links_by_type: dict[str, frozenset[str]]
    data_by_type: dict[str, frozenset[str]]


def index_multiplicity_facts(objects: dict[str, GraphObject]) -> IndexedMultiplicityFacts:
    """Index bounded object facts once, without expanding their neighborhood."""
    participants: dict[str, set[str]] = {}
    links: dict[str, set[str]] = {}
    data: dict[str, set[str]] = {}
    for uuid, value in objects.items():
        if isinstance(value, (Anchor, AssociatedDataObject)):
            participants.setdefault(value.type_key, set()).add(uuid)
        if isinstance(value, Link):
            links.setdefault(value.type_key, set()).add(uuid)
        if isinstance(value, AssociatedDataObject):
            data.setdefault(value.type_key, set()).add(uuid)
    return IndexedMultiplicityFacts(
        objects,
        {key: frozenset(values) for key, values in participants.items()},
        {key: frozenset(values) for key, values in links.items()},
        {key: frozenset(values) for key, values in data.items()},
    )


def derive_multiplicity_impact_reasons(
    neighborhood: ImpactNeighborhood,
    rules: tuple[RelationshipConstraint, ...],
) -> tuple[MultiplicityImpactReason, ...]:
    """Derive local reasons without crossing changed participants with unrelated rules."""
    reasons: set[MultiplicityImpactReason] = set()
    old_index = index_multiplicity_facts(neighborhood.old_objects)
    proposed_index = index_multiplicity_facts(neighborhood.proposed_objects)
    for rule in rules:
        rule_key = semantic_identity(relationship_identity(rule))
        end = rule.constrained_end.value
        old_contributions = _contributions(
            rule, old_index, neighborhood.examined_relationship_uuids
        )
        proposed_contributions = _contributions(
            rule, proposed_index, neighborhood.examined_relationship_uuids
        )

        membership_candidates = _subjects_for_rule(rule, old_index) | _subjects_for_rule(
            rule, proposed_index
        )
        membership_changed = {
            uuid
            for uuid in neighborhood.changed_participant_uuids & membership_candidates
            if _is_constrained_subject(rule, neighborhood.old_objects.get(uuid))
            != _is_constrained_subject(rule, neighborhood.proposed_objects.get(uuid))
        }
        reasons.update(
            MultiplicityImpactReason(rule_key, uuid, end, "subjectMembershipChanged")
            for uuid in membership_changed
        )

        for subject_uuid, _relationship_identity, carrier_uuid in (
            old_contributions ^ proposed_contributions
        ):
            if subject_uuid in membership_changed:
                reason: ReasonKind = "subjectMembershipChanged"
            elif carrier_uuid in neighborhood.changed_relationship_uuids:
                reason = "relationshipMembershipChanged"
            else:
                reason = "oppositeMembershipChanged"
            reasons.add(MultiplicityImpactReason(rule_key, subject_uuid, end, reason))
    return tuple(sorted(reasons))


def count_multiplicity_for_subjects(
    rule: RelationshipConstraint,
    facts: IndexedMultiplicityFacts,
    subject_uuids: frozenset[str],
    relationship_uuids: frozenset[str],
) -> dict[str, int]:
    """Count one rule only for its exact proposed constrained subjects."""
    counts = {
        uuid for uuid in subject_uuids if _is_constrained_subject(rule, facts.objects.get(uuid))
    }
    result = dict.fromkeys(counts, 0)
    for subject_uuid, _relationship_identity, _carrier_uuid in _contributions(
        rule, facts, relationship_uuids
    ):
        if subject_uuid in result:
            result[subject_uuid] += 1
    return result


def _subjects_for_rule(
    rule: RelationshipConstraint, facts: IndexedMultiplicityFacts
) -> frozenset[str]:
    if isinstance(rule, LinkMultiplicityConstraint):
        types = rule.constrained_endpoint_type_keys
    elif rule.constrained_end is DirectAssociationEnd.ANCHOR:
        types = rule.anchor_type_keys
    else:
        types = rule.associated_data_type_keys
    return frozenset().union(*(facts.participants_by_type.get(key, ()) for key in types))


def _is_constrained_subject(rule: RelationshipConstraint, value: GraphObject | None) -> bool:
    if isinstance(rule, LinkMultiplicityConstraint):
        return isinstance(value, (Anchor, AssociatedDataObject)) and (
            value.type_key in rule.constrained_endpoint_type_keys
        )
    if rule.constrained_end is DirectAssociationEnd.ANCHOR:
        return isinstance(value, Anchor) and value.type_key in rule.anchor_type_keys
    return isinstance(value, AssociatedDataObject) and (
        value.type_key in rule.associated_data_type_keys
    )


def _contributions(
    rule: RelationshipConstraint,
    facts: IndexedMultiplicityFacts,
    relationship_uuids: frozenset[str],
) -> set[tuple[str, str, str]]:
    if isinstance(rule, LinkMultiplicityConstraint):
        candidates = relationship_uuids & facts.links_by_type.get(rule.link_type_key, frozenset())
        return _link_contributions(rule, facts.objects, candidates)
    candidates = relationship_uuids & frozenset().union(
        *(facts.data_by_type.get(key, ()) for key in rule.associated_data_type_keys)
    )
    return _association_contributions(rule, facts.objects, candidates)


def _link_contributions(
    rule: LinkMultiplicityConstraint,
    objects: dict[str, GraphObject],
    relationship_uuids: frozenset[str],
) -> set[tuple[str, str, str]]:
    contributions: set[tuple[str, str, str]] = set()
    for relationship_uuid in relationship_uuids:
        relationship = objects.get(relationship_uuid)
        if not isinstance(relationship, Link) or relationship.type_key != rule.link_type_key:
            continue
        if rule.constrained_end is LinkEnd.SOURCE:
            subject_uuid, opposite_uuid = relationship.source_uuid, relationship.target_uuid
        else:
            subject_uuid, opposite_uuid = relationship.target_uuid, relationship.source_uuid
        subject = objects.get(subject_uuid)
        opposite = objects.get(opposite_uuid)
        if (
            isinstance(subject, (Anchor, AssociatedDataObject))
            and subject.type_key in rule.constrained_endpoint_type_keys
            and isinstance(opposite, (Anchor, AssociatedDataObject))
            and opposite.type_key in rule.opposite_endpoint_type_keys
        ):
            contributions.add((subject_uuid, relationship.uuid, relationship.uuid))
    return contributions


def _association_contributions(
    rule: DirectAssociationMultiplicityConstraint,
    objects: dict[str, GraphObject],
    relationship_uuids: frozenset[str],
) -> set[tuple[str, str, str]]:
    contributions: set[tuple[str, str, str]] = set()
    for relationship_uuid in relationship_uuids:
        data = objects.get(relationship_uuid)
        if not isinstance(data, AssociatedDataObject):
            continue
        if data.type_key not in rule.associated_data_type_keys:
            continue
        for anchor_uuid in data.anchor_uuids:
            anchor = objects.get(anchor_uuid)
            if not isinstance(anchor, Anchor) or anchor.type_key not in rule.anchor_type_keys:
                continue
            subject_uuid = (
                anchor_uuid if rule.constrained_end is DirectAssociationEnd.ANCHOR else data.uuid
            )
            # Direct associations have set identity by the data/anchor pair.
            relationship_uuid = semantic_identity((data.uuid, anchor_uuid))
            contributions.add((subject_uuid, relationship_uuid, data.uuid))
    return contributions
