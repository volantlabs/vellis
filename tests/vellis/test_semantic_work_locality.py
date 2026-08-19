"""Permanent locality and lifecycle evidence for ``vellis-2-semantic-work-locality``.

These tests reject forbidden population dependencies and transient-state lifetime regressions
without freezing superseded implementation shapes or historical exact costs.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.vellis.characterization import OWNER, measure
from tests.vellis.conftest import build_rich_definitions, build_rich_graph
from tests.vellis.test_sqlite_prospective_state import _assess_delta
from vellis.changes import GraphChange, GraphChangeRequest, GraphChangeTarget
from vellis.definitions import (
    AnchorTypeDefinition,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
)
from vellis.governance import ActivateDefinitionDeltaRequest, DefinitionChange
from vellis.graph import Anchor, Link
from vellis.history import ProspectiveSelection, RevisionSelection
from vellis.outcomes import (
    OperationStatus,
    ValidationFinding,
    ValidationRequest,
    ValidationRequestKind,
    ValidationScope,
)
from vellis.query import (
    AggregateQueryOutput,
    AggregationOperator,
    AnchorGroup,
    AssociatedDataCondition,
    GraphQuery,
    QueryAggregation,
    RequiredLink,
    UuidFilter,
)
from vellis.store import ActivityAppendError
from vellis.system import RTGSystem


class _InterleavingCursor:
    def __init__(
        self,
        cursor: sqlite3.Cursor,
        after_first_fetch: Callable[[], None],
    ) -> None:
        self._cursor = cursor
        self._after_first_fetch = after_first_fetch

    def fetchone(self) -> Any:
        row = self._cursor.fetchone()
        callback, self._after_first_fetch = self._after_first_fetch, lambda: None
        callback()
        return row

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class _InterleavingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        statement_prefix: str,
        after_first_fetch: Callable[[], None],
    ) -> None:
        self._connection = connection
        self._statement_prefix = statement_prefix
        self._after_first_fetch = after_first_fetch

    def execute(self, sql: str, parameters: Any = ()) -> Any:
        cursor = self._connection.execute(sql, parameters)
        if sql.startswith(self._statement_prefix):
            return _InterleavingCursor(cursor, self._after_first_fetch)
        return cursor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _active_hub_cost(
    tmp_path: Path, degree: int, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, int, int]:
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
        work_count: int | None = None
        original_clear = system.store._clear_transient_work_unlocked  # noqa: SLF001

        def capture_work_before_cleanup(*prefixes: str) -> None:
            nonlocal work_count
            if "multiplicity_" in prefixes:
                work_count = int(
                    system.store._connection.execute(  # noqa: SLF001
                        "SELECT count(*) FROM multiplicity_work"
                    ).fetchone()[0]
                )
            original_clear(*prefixes)

        with monkeypatch.context() as patch:
            patch.setattr(
                system.store, "_clear_transient_work_unlocked", capture_work_before_cleanup
            )
            measured = measure(
                system,
                lambda: system.apply_graph_change(
                    GraphChange(anchor_upserts=(Anchor("hub", "other", "Hub"),)),
                    provenance=OWNER,
                ),
            )
        assert measured.value.accepted, measured.value.findings
        assert work_count is not None
        return (
            measured.cost.sqlite_vm_steps,
            measured.cost.current_graph_object_decodes,
            work_count,
        )
    finally:
        system.close()


def test_active_endpoint_type_work_scales_with_applicable_degree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    costs = [_active_hub_cost(tmp_path, degree, monkeypatch) for degree in (10, 20, 40)]

    assert [work for _steps, _decodes, work in costs] == [1, 1, 1]
    for (small_steps, small_decodes, _), (large_steps, large_decodes, _) in zip(
        costs, costs[1:], strict=False
    ):
        assert large_steps < small_steps * 3
        assert large_decodes < small_decodes * 3


def _irrelevant_rule_cost(tmp_path: Path, count: int) -> tuple[int, int]:
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
        work_counts: list[int] = []
        original_clear = system.store._clear_assessment_work_unlocked  # noqa: SLF001

        def capture_then_clear() -> None:
            work_counts.append(
                int(
                    system.store._connection.execute(  # noqa: SLF001
                        "SELECT count(*) FROM multiplicity_work"
                    ).fetchone()[0]
                )
            )
            original_clear()

        system.store._clear_assessment_work_unlocked = capture_then_clear  # type: ignore[method-assign]  # noqa: SLF001
        measured = measure(system, lambda: _assess_delta(system))
        assert measured.value.conforms
        assert work_counts
        return measured.cost.sqlite_vm_steps, work_counts[-1]
    finally:
        system.close()


def test_display_only_edit_has_zero_rule_population_dependency(tmp_path: Path) -> None:
    costs = [_irrelevant_rule_cost(tmp_path, count) for count in (10, 100, 500, 1_000)]

    assert [work for _steps, work in costs] == [0, 0, 0, 0]
    assert len({steps for steps, _work in costs}) == 1


def _independent_change_rule_cost(tmp_path: Path, count: int) -> tuple[int, int]:
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
        work_counts: list[int] = []
        original_clear = system.store._clear_assessment_work_unlocked  # noqa: SLF001

        def capture_then_clear() -> None:
            work_counts.append(
                int(
                    system.store._connection.execute(  # noqa: SLF001
                        "SELECT count(*) FROM multiplicity_work"
                    ).fetchone()[0]
                )
            )
            original_clear()

        system.store._clear_assessment_work_unlocked = capture_then_clear  # type: ignore[method-assign]  # noqa: SLF001
        measured = measure(system, lambda: _assess_delta(system))
        assert measured.value.conforms
        assert work_counts
        return measured.cost.sqlite_vm_steps, work_counts[-1]
    finally:
        system.close()


def test_independent_changes_produce_one_exact_work_tuple_each(tmp_path: Path) -> None:
    costs = [_independent_change_rule_cost(tmp_path, count) for count in (5, 10, 20, 40)]

    assert [work for _steps, work in costs] == [5, 10, 20, 40]
    for (small_steps, _), (large_steps, _) in zip(costs, costs[1:], strict=False):
        assert large_steps < small_steps * 3


def test_compiled_binding_preflight_refuses_all_states_at_the_same_limit(tmp_path: Path) -> None:
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
                UuidFilter((person.uuid,)) if index < 2 else None,
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
            output=AggregateQueryOutput(
                kind="aggregates",
                data_condition="notes",
                aggregations=(QueryAggregation("count", AggregationOperator.COUNT),),
                maximum_matches=20,
            ),
        )
        system.store._connection.setlimit(  # noqa: SLF001
            sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 32
        )

        current = system.query_graph(query, provenance=OWNER)
        prospective = system.query_graph(
            replace(query, state=ProspectiveSelection(kind="prospective")), provenance=OWNER
        )
        historical = system.query_graph(
            replace(
                query,
                state=RevisionSelection(kind="revision", revision=applied.resulting_revision),
            ),
            provenance=OWNER,
        )

        for result in (current, prospective, historical):
            assert result.status is OperationStatus.REJECTED
            assert not result.rows and not result.aggregates
            assert result.evaluated_revision is None
            assert "parameters" in result.findings[0].summary
    finally:
        system.close()


def test_definition_summary_uses_one_committed_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mixed-definition-summary.sqlite3"
    first = RTGSystem.open(path)
    second = RTGSystem.open(path)
    try:
        assert first.initialize_fresh(
            GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
            provenance=OWNER,
            initialization_summary="mixed definition summary trigger",
        ).accepted
        assert first.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("team", "A team."),)),
            provenance=OWNER,
        ).accepted
        original = first.store._definition_selection_context_unlocked  # noqa: SLF001

        def interleaved(*, prospective: bool, revision: int | None):
            context = original(prospective=prospective, revision=revision)
            assessment = second.check(
                ValidationRequest(
                    ValidationRequestKind.ASSESS,
                    ValidationScope.DEFINITION_DELTA,
                    maximum_findings=10,
                ),
                provenance=OWNER,
            )
            assert assessment.accepted and assessment.assessment_id is not None
            activated = second.activate_definition_delta(
                ActivateDefinitionDeltaRequest(assessment.assessment_id),
                provenance=OWNER,
            )
            assert activated.accepted and activated.resulting_revision == 2
            return context

        monkeypatch.setattr(
            first.store,
            "_definition_selection_context_unlocked",
            interleaved,
        )

        evaluated_revision, rows, delta_present = first.store.definition_summary_rows()

        assert evaluated_revision == 1
        assert rows == (("person", "A person."),)
        assert delta_present
        assert first.store.current_revision() == 2
    finally:
        first.close()
        second.close()


def test_definition_inspection_source_uses_one_committed_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "definition-neighborhood-snapshot.sqlite3"
    first = RTGSystem.open(path)
    second = RTGSystem.open(path)
    try:
        assert first.initialize_fresh(
            GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "Before"),)),
            provenance=OWNER,
            initialization_summary="definition neighborhood snapshot",
        ).accepted
        assert first.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("person", "After"),)),
            provenance=OWNER,
        ).accepted
        original = first.store._definition_selection_context_unlocked  # noqa: SLF001

        def interleaved(*, prospective: bool, revision: int | None):
            context = original(prospective=prospective, revision=revision)
            assessment = second.check(
                ValidationRequest(
                    ValidationRequestKind.ASSESS,
                    ValidationScope.DEFINITION_DELTA,
                    maximum_findings=10,
                ),
                provenance=OWNER,
            )
            assert assessment.assessment_id is not None
            assert second.activate_definition_delta(
                ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
            ).accepted
            return context

        monkeypatch.setattr(first.store, "_definition_selection_context_unlocked", interleaved)
        revision, definitions, delta_present = first.store.definition_neighborhood(("person",))

        assert revision == 1 and delta_present
        assert definitions.anchor_types == (AnchorTypeDefinition("person", "Before"),)
        assert first.store.current_revision() == 2
    finally:
        first.close()
        second.close()


def test_proposal_discovery_uses_one_committed_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "proposal-discovery-snapshot.sqlite3"
    first = RTGSystem.open(path)
    second = RTGSystem.open(path)
    try:
        assert first.initialize_fresh(
            GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
            provenance=OWNER,
            initialization_summary="proposal discovery snapshot",
        ).accepted
        assert first.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("team", "A team."),)),
            provenance=OWNER,
        ).accepted
        assessment = second.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.DEFINITION_DELTA,
                maximum_findings=10,
            ),
            provenance=OWNER,
        )
        assessment_id = assessment.assessment_id
        assert assessment_id is not None
        original = first.store._overlay_identity_unlocked  # noqa: SLF001

        def interleaved() -> str:
            identity = original()
            assert second.activate_definition_delta(
                ActivateDefinitionDeltaRequest(assessment_id), provenance=OWNER
            ).accepted
            return identity

        monkeypatch.setattr(first.store, "_overlay_identity_unlocked", interleaved)
        state = first.store.proposal_state()

        assert state.revision == 1
        assert state.proposed_definition_identity is not None
        assert first.store.current_revision() == 2
    finally:
        first.close()
        second.close()


def test_assessment_page_uses_one_snapshot_during_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mixed-assessment-page.sqlite3"
    first = RTGSystem.open(path)
    second = RTGSystem.open(path)
    try:
        assert first.initialize_fresh(
            GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
            provenance=OWNER,
            initialization_summary="mixed assessment page trigger",
        ).accepted
        prior = second.store.publish_assessment(
            ValidationScope.GRAPH_CONFORMANCE,
            0,
            iter(
                (
                    ValidationFinding("first"),
                    ValidationFinding("second"),
                    ValidationFinding("third"),
                )
            ),
            maximum_findings=3,
        )
        assert prior.assessment_id is not None

        def replace_assessment() -> None:
            replacement = second.store.publish_assessment(
                ValidationScope.GRAPH_CONFORMANCE,
                0,
                iter((ValidationFinding("replacement"),)),
                maximum_findings=1,
            )
            assert replacement.assessment_id != prior.assessment_id

        proxy = _InterleavingConnection(
            first.store._connection,  # noqa: SLF001
            "SELECT scope, evaluated_revision",
            replace_assessment,
        )
        monkeypatch.setattr(
            first.store,
            "_connection",
            cast(sqlite3.Connection, proxy),
        )

        report = first.store.assessment_page(prior.assessment_id, 1, 3)

        assert report is not None
        assert report.assessment_id == prior.assessment_id
        assert report.finding_count == 3
        assert tuple(finding.summary for finding in report.returned_findings) == (
            "first",
            "second",
            "third",
        )
        assert report.returned_start_ordinal == 1
        assert not report.more_findings
    finally:
        first.close()
        second.close()


def _temporary_work_counts(connection: sqlite3.Connection, prefix: str) -> dict[str, int]:
    names = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_temp_master WHERE type = 'table' AND name LIKE ?"
            " ORDER BY name",
            (f"{prefix}%",),
        )
    )
    return {
        name: int(connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0])
        for name in names
    }


def _seed_test_multiplicity_residue(connection: sqlite3.Connection) -> None:
    """Populate reusable work relations explicitly for assessment-cleanup evidence."""
    connection.execute(
        "INSERT INTO multiplicity_impact_reason VALUES"
        " ('test-rule', 'test-subject', 'source', 'subjectMembershipChanged')"
    )
    connection.execute(
        "INSERT INTO multiplicity_work VALUES ('test-rule', 'test-subject', 'source')"
    )


@pytest.mark.parametrize("change_size", (50, 2_000))
def test_active_graph_change_clears_multiplicity_work_after_every_exit(
    tmp_path: Path, change_size: int
) -> None:
    system = RTGSystem.open(tmp_path / f"active-work-cleanup-{change_size}.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
            provenance=OWNER,
            initialization_summary="active mutation work cleanup",
        ).accepted
        accepted = system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(
                    Anchor(f"person-{index}", "person", f"Person {index}")
                    for index in range(change_size)
                )
            ),
            provenance=OWNER,
        )
        assert accepted.accepted
        connection = system.store._connection  # noqa: SLF001
        counts = _temporary_work_counts(connection, "multiplicity_")
        assert counts
        assert all(count == 0 for count in counts.values())

        rejected = system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("unknown", "unknown", "Unknown"),)),
            provenance=OWNER,
        )
        assert rejected.status is OperationStatus.REJECTED
        assert all(
            count == 0 for count in _temporary_work_counts(connection, "multiplicity_").values()
        )

        _seed_test_multiplicity_residue(connection)
        connection.execute(
            "CREATE TEMP TRIGGER fail_active_validation_work BEFORE INSERT"
            " ON multiplicity_subject_seed"
            " BEGIN SELECT RAISE(ABORT, 'active validation failure'); END"
        )
        failed = system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("failure", "person", "Failure"),)),
            provenance=OWNER,
        )
        assert failed.status is OperationStatus.FAILED
        assert all(
            count == 0 for count in _temporary_work_counts(connection, "multiplicity_").values()
        )
        connection.execute("DROP TRIGGER fail_active_validation_work")
    finally:
        system.close()


def test_assessment_and_restore_clear_population_work_after_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = RTGSystem.open(tmp_path / "retained-work-rows.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
            provenance=OWNER,
            initialization_summary="retained work rows trigger",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(
                    Anchor(f"person-{index}", "person", f"Person {index}") for index in range(3)
                )
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(type_removals=("person",)),
            provenance=OWNER,
        ).accepted
        connection = system.store._connection  # noqa: SLF001
        _seed_test_multiplicity_residue(connection)
        initial_residue = _temporary_work_counts(connection, "multiplicity_")
        assert any(count > 0 for count in initial_residue.values())

        connection.execute(
            "CREATE TRIGGER fail_assessment_cleanup_evidence BEFORE INSERT"
            " ON current_assessment BEGIN SELECT RAISE(ABORT, 'assessment failure'); END"
        )
        failed_assessment = system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.DEFINITION_DELTA,
                maximum_findings=10,
            ),
            provenance=OWNER,
        )
        assert not failed_assessment.accepted
        assert all(
            count == 0 for count in _temporary_work_counts(connection, "assessment_").values()
        )
        assert all(
            count == 0 for count in _temporary_work_counts(connection, "multiplicity_").values()
        )
        connection.execute("DROP TRIGGER fail_assessment_cleanup_evidence")

        # Exercise the separate activity-observation failure branch from deliberate
        # test-owned residue rather than relying on completed active-mutation work.
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("person-extra", "person", "Extra"),)),
            provenance=OWNER,
        ).accepted
        _seed_test_multiplicity_residue(connection)
        activity_residue = _temporary_work_counts(connection, "multiplicity_")
        assert any(count > 0 for count in activity_residue.values())

        def fail_activity(_record: object) -> None:
            raise ActivityAppendError("injected assessment activity failure")

        with monkeypatch.context() as patch:
            patch.setattr(system.store, "_append_activity_unlocked", fail_activity)
            with pytest.raises(ActivityAppendError, match="injected assessment activity failure"):
                system.check(
                    ValidationRequest(
                        ValidationRequestKind.ASSESS,
                        ValidationScope.DEFINITION_DELTA,
                        maximum_findings=10,
                    ),
                    provenance=OWNER,
                )
        assert all(
            count == 0 for count in _temporary_work_counts(connection, "assessment_").values()
        )
        assert all(
            count == 0 for count in _temporary_work_counts(connection, "multiplicity_").values()
        )

        assessment = system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.DEFINITION_DELTA,
                maximum_findings=10,
            ),
            provenance=OWNER,
        )
        assert assessment.accepted
        assessment_counts = _temporary_work_counts(connection, "assessment_")
        multiplicity_counts = _temporary_work_counts(connection, "multiplicity_")
        assert assessment_counts
        assert all(count == 0 for count in assessment_counts.values())
        assert all(count == 0 for count in multiplicity_counts.values())

        assert system.discard_definition_delta(provenance=OWNER).accepted
        connection.execute(
            "CREATE TRIGGER fail_restore_cleanup_evidence BEFORE INSERT"
            " ON canonical_graph_event"
            " BEGIN SELECT RAISE(ABORT, 'restore failure'); END"
        )
        failed_restore = system.restore_historical_state(
            RevisionSelection(kind="revision", revision=0),
            provenance=OWNER,
        )
        assert not failed_restore.accepted
        assert all(count == 0 for count in _temporary_work_counts(connection, "restore_").values())
        connection.execute("DROP TRIGGER fail_restore_cleanup_evidence")

        restored = system.restore_historical_state(
            RevisionSelection(kind="revision", revision=0),
            provenance=OWNER,
        )
        assert restored.accepted
        restore_counts = _temporary_work_counts(connection, "restore_")
        assert set(restore_counts) == {"restore_candidate", "restore_current", "restore_target"}
        assert all(count == 0 for count in restore_counts.values())
    finally:
        system.close()
