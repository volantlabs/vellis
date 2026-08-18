"""Executable trigger evidence for ``vellis-2-semantic-work-locality``.

These tests characterize the conflicting baseline so W001 evidence is reconstructible.
W002-W004 replace them with target-conformance regressions; W005 removes assertions that
depend on a superseded implementation shape.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

import vellis.definitions as definitions_module
from tests.vellis.characterization import OWNER, measure
from tests.vellis.conftest import build_rich_definitions, build_rich_graph
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
from vellis.governance import DefinitionChange
from vellis.graph import Anchor, Link
from vellis.history import RevisionSelection
from vellis.json_value import normalize
from vellis.outcomes import OperationStatus
from vellis.query import (
    AggregationOperator,
    AnchorGroup,
    AnchorUuidFilter,
    AssociatedDataCondition,
    EvaluatedStateScope,
    GraphQuery,
    QueryAggregation,
    RequiredLink,
    ReturnShape,
)
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


def test_historical_aggregate_reproduces_missing_limit_binding_preflight(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "historical-capacity.sqlite3")
    try:
        assert system.initialize_fresh(
            build_rich_definitions(),
            provenance=OWNER,
            initialization_summary="historical capacity trigger",
        ).accepted
        rich_graph = build_rich_graph()
        people = (
            rich_graph.anchors[0],
            *(Anchor(f"person-{index}", "person", f"Person {index}") for index in range(2, 7)),
        )
        project = rich_graph.anchors[1]
        links = tuple(
            Link(f"works-{index}", "worksOn", person.uuid, project.uuid)
            for index, person in enumerate(people)
        )
        applied = system.apply_graph_change(
            GraphChange(
                anchor_upserts=(*people, project),
                associated_data_upserts=rich_graph.associated_data,
                link_upserts=links,
            ),
            provenance=OWNER,
        )
        assert applied.accepted and applied.resulting_revision is not None
        assert system.set_definition_delta(
            DefinitionChange(
                anchor_type_upserts=(AnchorTypeDefinition("unrelated", "An unrelated type."),)
            ),
            provenance=OWNER,
        ).accepted
        groups = tuple(
            AnchorGroup(
                f"person{index}",
                ("person",),
                AnchorUuidFilter((person.uuid,)) if index < 2 else None,
            )
            for index, person in enumerate(people)
        ) + (AnchorGroup("project", ("project",)),)
        query = GraphQuery(
            anchor_groups=groups,
            data_conditions=(AssociatedDataCondition("notes", "person0", "note"),),
            required_links=tuple(
                RequiredLink(f"link{index}", f"person{index}", "project", "worksOn")
                for index in range(len(people))
            ),
            return_shape=ReturnShape(()),
            aggregations=(
                QueryAggregation("count", AggregationOperator.COUNT, "notes"),
            ),
            maximum_rows=20,
        )
        system.store._connection.setlimit(  # noqa: SLF001
            sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 32
        )

        current = system.query_graph(query, provenance=OWNER)
        prospective = system.query_graph(
            replace(query, state_scope=EvaluatedStateScope.PROSPECTIVE), provenance=OWNER
        )
        historical = system.query_graph(
            replace(query, state_scope=EvaluatedStateScope.HISTORICAL),
            selection=RevisionSelection(applied.resulting_revision),
            provenance=OWNER,
        )

        assert current.status is OperationStatus.ACCEPTED
        assert prospective.status is OperationStatus.ACCEPTED
        assert historical.status is OperationStatus.FAILED
        assert "too many SQL variables" in historical.findings[0].summary
        assert not historical.rows and not historical.aggregates
        assert historical.evaluated_revision is None
    finally:
        system.close()


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
