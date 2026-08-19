"""Exact old/proposed multiplicity-impact evidence independent of SQLite planning."""

from vellis.definitions import (
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    LinkEnd,
    LinkMultiplicityConstraint,
    relationship_identity,
)
from vellis.graph import Anchor, AssociatedDataObject, Link
from vellis.mutation_impact import ImpactNeighborhood, derive_multiplicity_impact_reasons
from vellis.normalized import semantic_identity


def _reason_rows(neighborhood: ImpactNeighborhood, rule):
    return tuple(
        (reason.rule_key, reason.subject_uuid, reason.constrained_end, reason.reason_kind)
        for reason in derive_multiplicity_impact_reasons(neighborhood, (rule,))
    )


def test_link_insertion_changes_only_its_exact_constrained_subject() -> None:
    rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("subject",), ("opposite",), 0, None, "Edges."
    )
    subject = Anchor("subject", "subject", "Subject")
    opposite = Anchor("opposite", "opposite", "Opposite")
    edge = Link("edge", "edge", "subject", "opposite")
    key = semantic_identity(relationship_identity(rule))

    reasons = _reason_rows(
        ImpactNeighborhood(
            {subject.uuid: subject, opposite.uuid: opposite},
            {subject.uuid: subject, opposite.uuid: opposite, edge.uuid: edge},
            frozenset({edge.uuid}),
            frozenset({edge.uuid}),
            frozenset(),
        ),
        rule,
    )

    assert reasons == ((key, "subject", "source", "relationshipMembershipChanged"),)


def test_subject_and_opposite_membership_changes_have_distinct_reasons() -> None:
    rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("subject",), ("opposite",), 0, None, "Edges."
    )
    edge = Link("edge", "edge", "subject", "opposite")
    opposite = Anchor("opposite", "opposite", "Opposite")
    key = semantic_identity(relationship_identity(rule))

    subject_reasons = _reason_rows(
        ImpactNeighborhood(
            {
                "subject": Anchor("subject", "outside", "Subject"),
                "opposite": opposite,
                "edge": edge,
            },
            {
                "subject": Anchor("subject", "subject", "Subject"),
                "opposite": opposite,
                "edge": edge,
            },
            frozenset({"edge"}),
            frozenset(),
            frozenset({"subject"}),
        ),
        rule,
    )
    opposite_reasons = _reason_rows(
        ImpactNeighborhood(
            {
                "subject": Anchor("subject", "subject", "Subject"),
                "opposite": opposite,
                "edge": edge,
            },
            {
                "subject": Anchor("subject", "subject", "Subject"),
                "opposite": Anchor("opposite", "outside", "Opposite"),
                "edge": edge,
            },
            frozenset({"edge"}),
            frozenset(),
            frozenset({"opposite"}),
        ),
        rule,
    )

    assert subject_reasons == ((key, "subject", "source", "subjectMembershipChanged"),)
    assert opposite_reasons == ((key, "subject", "source", "oppositeMembershipChanged"),)


def test_direct_association_move_enqueues_only_old_and_new_anchors() -> None:
    rule = DirectAssociationMultiplicityConstraint(
        DirectAssociationEnd.ANCHOR,
        ("anchor",),
        ("data",),
        0,
        None,
        "Direct associations.",
    )
    first = Anchor("first", "anchor", "First")
    second = Anchor("second", "anchor", "Second")
    old_data = AssociatedDataObject("data", "data", ("first",), {})
    new_data = AssociatedDataObject("data", "data", ("second",), {})
    key = semantic_identity(relationship_identity(rule))

    reasons = _reason_rows(
        ImpactNeighborhood(
            {"first": first, "second": second, "data": old_data},
            {"first": first, "second": second, "data": new_data},
            frozenset({"data"}),
            frozenset({"data"}),
            frozenset(),
        ),
        rule,
    )

    assert reasons == (
        (key, "first", "anchor", "relationshipMembershipChanged"),
        (key, "second", "anchor", "relationshipMembershipChanged"),
    )


def test_direct_association_opposite_type_change_is_not_a_relationship_change() -> None:
    rule = DirectAssociationMultiplicityConstraint(
        DirectAssociationEnd.ANCHOR,
        ("anchor",),
        ("eligible",),
        0,
        None,
        "Eligible data associations.",
    )
    anchor = Anchor("anchor", "anchor", "Anchor")
    old_data = AssociatedDataObject("data", "eligible", ("anchor",), {})
    new_data = AssociatedDataObject("data", "ineligible", ("anchor",), {})
    key = semantic_identity(relationship_identity(rule))

    reasons = _reason_rows(
        ImpactNeighborhood(
            {"anchor": anchor, "data": old_data},
            {"anchor": anchor, "data": new_data},
            frozenset({"data"}),
            frozenset(),
            frozenset({"data"}),
        ),
        rule,
    )

    assert reasons == ((key, "anchor", "anchor", "oppositeMembershipChanged"),)
