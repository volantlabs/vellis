"""Executable trigger evidence for ``vellis-2-semantic-work-locality``.

These tests characterize the conflicting baseline so W001 evidence is reconstructible.
W002-W004 replace them with target-conformance regressions; W005 removes assertions that
depend on a superseded implementation shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import vellis.definitions as definitions_module
from tests.vellis.characterization import OWNER, measure
from tests.vellis.test_sqlite_prospective_state import _assess_delta
from vellis.changes import GraphChange, GraphChangeRequest, GraphChangeTarget
from vellis.definitions import (
    AnchorTypeDefinition,
    EndpointConstraint,
    GraphDefinitionSet,
    JsonKind,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    PropertyConstraint,
    ValueRange,
    validate_definition_set,
)
from vellis.graph import Anchor, Link
from vellis.json_value import normalize
from vellis.system import RTGSystem


def _active_hub_cost(tmp_path: Path, degree: int) -> tuple[int, int]:
    central = AnchorTypeDefinition("central", "A central node.")
    other = AnchorTypeDefinition("other", "Another node.")
    spoke = AnchorTypeDefinition("spoke", "A spoke node.")
    leaf = AnchorTypeDefinition("leaf", "A leaf node.")
    edge = LinkTypeDefinition(
        "edge",
        EndpointConstraint(("central", "other", "spoke"), ("spoke", "leaf"), "Ends."),
        "An edge.",
    )
    rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("central",), ("spoke",), 0, None, "Central edges."
    )
    system = RTGSystem.open(tmp_path / f"active-hub-{degree}.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(central, other, spoke, leaf),
                link_types=(edge,),
                relationship_constraints=(rule,),
            ),
            provenance=OWNER,
            initialization_summary="active hub trigger",
        ).accepted
        anchors = [Anchor("hub", "central", "Hub")]
        links: list[Link] = []
        for spoke_index in range(degree):
            spoke_uuid = f"spoke-{spoke_index}"
            anchors.append(Anchor(spoke_uuid, "spoke", spoke_uuid))
            links.append(Link(f"hub-{spoke_index}", "edge", "hub", spoke_uuid))
            for leaf_index in range(degree):
                leaf_uuid = f"leaf-{spoke_index}-{leaf_index}"
                anchors.append(Anchor(leaf_uuid, "leaf", leaf_uuid))
                links.append(
                    Link(f"spoke-leaf-{spoke_index}-{leaf_index}", "edge", spoke_uuid, leaf_uuid)
                )
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=tuple(anchors), link_upserts=tuple(links)),
            provenance=OWNER,
        ).accepted
        measured = measure(
            system,
            lambda: system.apply_graph_change(
                GraphChange(anchor_upserts=(Anchor("hub", "other", "Hub"),)),
                provenance=OWNER,
            ),
        )
        assert measured.value.accepted, measured.value.findings
        return measured.cost.sqlite_vm_steps, measured.cost.current_graph_object_decodes
    finally:
        system.close()


def test_active_endpoint_type_trigger_reproduces_quadratic_neighbor_work(tmp_path: Path) -> None:
    costs = [_active_hub_cost(tmp_path, degree) for degree in (10, 20, 40)]

    assert costs == [(15_187, 231), (52_857, 861), (200_389, 3_321)]
    for (small_steps, small_decodes), (large_steps, large_decodes) in zip(
        costs, costs[1:], strict=False
    ):
        assert large_steps > small_steps * 3
        assert large_decodes > small_decodes * 3


def _irrelevant_rule_cost(tmp_path: Path, count: int) -> int:
    subject = AnchorTypeDefinition("subject", "A subject.")
    opposite = AnchorTypeDefinition("opposite", "An opposite.")
    link_types = tuple(
        LinkTypeDefinition(
            f"edge-{index}",
            EndpointConstraint(("subject",), ("opposite",), f"Ends {index}."),
            f"Edge {index}.",
        )
        for index in range(count)
    )
    rules = tuple(
        LinkMultiplicityConstraint(
            link.type_key,
            LinkEnd.SOURCE,
            ("subject",),
            ("opposite",),
            0,
            None,
            f"Rule {index}.",
        )
        for index, link in enumerate(link_types)
    )
    system = RTGSystem.open(tmp_path / f"irrelevant-rules-{count}.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(subject, opposite),
                link_types=link_types,
                relationship_constraints=rules,
            ),
            provenance=OWNER,
            initialization_summary="irrelevant rule trigger",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("subject", "subject", "Before"),)),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("subject", "subject", "After"),)),
            ),
            provenance=OWNER,
        ).accepted
        measured = measure(system, lambda: _assess_delta(system))
        assert measured.value.conforms
        return measured.cost.sqlite_vm_steps
    finally:
        system.close()


def test_display_only_trigger_reproduces_irrelevant_rule_dependency(tmp_path: Path) -> None:
    costs = [_irrelevant_rule_cost(tmp_path, count) for count in (10, 100, 500, 1_000)]

    assert costs == [8_434, 45_154, 208_354, 412_354]
    assert costs == sorted(costs)
    assert costs[-1] > costs[0] * 20


def _independent_change_rule_cost(tmp_path: Path, count: int) -> int:
    anchor_types = []
    link_types = []
    rules = []
    current_anchors = []
    changed_anchors = []
    for index in range(count):
        old_type = f"old-{index}"
        new_type = f"new-{index}"
        opposite_type = f"opposite-{index}"
        link_type = f"edge-{index}"
        anchor_types.extend(
            (
                AnchorTypeDefinition(old_type, f"Old {index}."),
                AnchorTypeDefinition(new_type, f"New {index}."),
                AnchorTypeDefinition(opposite_type, f"Opposite {index}."),
            )
        )
        link_types.append(
            LinkTypeDefinition(
                link_type,
                EndpointConstraint((old_type, new_type), (opposite_type,), f"Ends {index}."),
                f"Edge {index}.",
            )
        )
        rules.append(
            LinkMultiplicityConstraint(
                link_type,
                LinkEnd.SOURCE,
                (old_type,),
                (opposite_type,),
                0,
                None,
                f"Rule {index}.",
            )
        )
        current_anchors.append(Anchor(f"subject-{index}", old_type, f"Subject {index}"))
        changed_anchors.append(Anchor(f"subject-{index}", new_type, f"Subject {index}"))

    system = RTGSystem.open(tmp_path / f"independent-{count}.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=tuple(anchor_types),
                link_types=tuple(link_types),
                relationship_constraints=tuple(rules),
            ),
            provenance=OWNER,
            initialization_summary="independent change trigger",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=tuple(current_anchors)), provenance=OWNER
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=tuple(changed_anchors)),
            ),
            provenance=OWNER,
        ).accepted
        measured = measure(system, lambda: _assess_delta(system))
        assert measured.value.conforms
        return measured.cost.sqlite_vm_steps
    finally:
        system.close()


def test_independent_changes_reproduce_participant_by_rule_cross_product(tmp_path: Path) -> None:
    costs = [_independent_change_rule_cost(tmp_path, count) for count in (5, 10, 20, 40)]

    assert costs == [13_498, 31_543, 93_133, 318_313]
    assert costs[-1] > costs[-2] * 3


@pytest.mark.parametrize("count", [500, 1_000, 2_000, 4_000, 8_000])
def test_permitted_value_trigger_reproduces_pairwise_equality(monkeypatch, count: int) -> None:
    calls = 0
    original = definitions_module.json_equal

    def counted(left, right):
        nonlocal calls
        calls += 1
        return original(left, right)

    monkeypatch.setattr(definitions_module, "json_equal", counted)
    constraint = PropertyConstraint(
        property_name="choice",
        required=False,
        json_kind=JsonKind.STRING,
        value_range=ValueRange(
            permitted_values=tuple(normalize(f"value-{index}") for index in range(count))
        ),
        description="A choice.",
    )
    graph_definitions = GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition("anchor", "An anchor."),),
    )

    # Exercise the private rule directly so unrelated definition checks do not obscure
    # the exact uniqueness comparison count.
    findings = []
    definitions_module._check_permitted_values(  # noqa: SLF001
        constraint, constraint.value_range, "choice", findings
    )

    assert not findings
    assert calls == count * (count - 1) // 2
    assert not validate_definition_set(graph_definitions)


def test_trigger_source_contains_late_distinct_false_oracle_and_manual_capacity() -> None:
    root = Path(__file__).parents[2]
    store_source = (root / "vellis" / "store.py").read_text(encoding="utf-8")
    query_source = (root / "vellis" / "query.py").read_text(encoding="utf-8")
    oracle_source = (root / "tests" / "vellis" / "oracle.py").read_text(encoding="utf-8")

    aggregation = store_source[store_source.index("def _aggregate_bindings_unlocked") :]
    capacity = store_source[
        store_source.index("def _query_capacity_finding_unlocked") :
        store_source.index("def _clear_query_filter_tables_unlocked")
    ]
    prospective = store_source[
        store_source.index("def _iter_multiplicity_findings_unlocked") :
        store_source.index("def _multiplicity_findings_unlocked")
    ]

    assert "SELECT DISTINCT" in aggregation
    assert "LIMIT ?" in aggregation
    assert "historical_selection" not in capacity
    assert "assessment_impacted_type" in prospective
    assert "SELECT ?, uuid FROM assessment_type_changed_participant" in prospective
    assert "def evaluate_indexed_query" in query_source
    assert "evaluate_indexed_query" in oracle_source
