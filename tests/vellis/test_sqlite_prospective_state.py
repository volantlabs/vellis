"""Evidence for SQLite-native prospective state, stored assessments, and cutover."""

import random
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from tests.vellis.oracle import materialize_definitions, materialize_replay, materialize_state
from tests.vellis.semantic_state import (
    DefinitionDelta,
    definition_delta_equal,
    semantic_state_equal,
)
from vellis.activity import HistoryKind, HistoryQuery
from vellis.canonical import Provenance
from vellis.changes import GraphChange, GraphChangeRequest, GraphChangeTarget
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    relationship_identity,
    validate_definition_set,
)
from vellis.discovery import DefinitionInspectionRequest, DefinitionSummaryRequest
from vellis.governance import (
    ActivateDefinitionDeltaRequest,
    DefinitionChange,
)
from vellis.graph import Anchor, AssociatedDataObject, Link, SystemMetadata
from vellis.history import ProspectiveSelection
from vellis.normalized import definition_identity, semantic_identity
from vellis.outcomes import ValidationRequest, ValidationRequestKind, ValidationScope
from vellis.query import (
    AnchorGroup,
    AnchorProjection,
    GraphQuery,
    RowQueryOutput,
)
from vellis.system import RTGSystem
from vellis.validation import assess_object_neighborhood

OWNER = Provenance("owner")
PERSON = AnchorTypeDefinition("person", "A person.")
TEAM = AnchorTypeDefinition("team", "A team.")


def _system(tmp_path: Path) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        GraphDefinitionSet(anchor_types=(PERSON,)),
        provenance=OWNER,
        initialization_summary="fresh",
    ).accepted
    return system


def _assess_delta(system: RTGSystem, maximum: int = 10):
    return system.check(
        ValidationRequest(
            ValidationRequestKind.ASSESS,
            ValidationScope.DEFINITION_DELTA,
            maximum,
        )
    )


def _complete_prospective_graph_findings(system: RTGSystem):
    connection = system.store._connection  # noqa: SLF001
    active_identity = str(
        connection.execute(
            "SELECT active_definition_set_id FROM state_head WHERE id = 0"
        ).fetchone()[0]
    )
    type_keys = {
        str(row[0])
        for row in connection.execute(
            "SELECT type_key FROM current_definition_type_source"
            " UNION SELECT type_key FROM proposal_definition_type"
        )
    }
    relationship_keys = {
        str(row[0])
        for row in connection.execute(
            "SELECT natural_key FROM current_definition_relationship_source"
            " UNION SELECT natural_key FROM proposal_definition_relationship"
        )
    }
    definitions = system.store._effective_proposed_definitions_unlocked(  # noqa: SLF001
        active_identity,
        type_keys=type_keys,
        constrained_type_keys=set(),
        relationship_keys=relationship_keys,
    )
    objects = tuple(
        system.store._load_object_value(int(value_id))  # noqa: SLF001
        for (value_id,) in connection.execute(
            "SELECT object_value_id FROM prospective_graph_object ORDER BY uuid"
        )
    )
    return assess_object_neighborhood(objects, definitions)


def test_large_multiplicity_participant_sets_are_bound_relationally(tmp_path: Path) -> None:
    anchors = tuple(
        AnchorTypeDefinition(f"anchor-{index}", f"Anchor {index}.") for index in range(40)
    )
    data = AssociatedDataTypeDefinition(
        "datum",
        tuple(value.type_key for value in anchors),
        description="Associated data.",
    )
    constraint = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=tuple(value.type_key for value in anchors),
        associated_data_type_keys=("datum",),
        lower_bound=0,
        upper_bound=1,
        description="At most one datum.",
    )
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        GraphDefinitionSet(
            anchor_types=anchors,
            associated_data_types=(data,),
            relationship_constraints=(constraint,),
        ),
        provenance=OWNER,
        initialization_summary="many multiplicity participants",
    ).accepted
    system.store._connection.setlimit(  # noqa: SLF001
        sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 32
    )
    try:
        report = system.check(provenance=OWNER)

        assert report.accepted, report.findings
        assert report.conforms is True
    finally:
        system.close()


def test_large_prospective_change_does_not_depend_on_sqlite_host_parameters(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        system.store._connection.setlimit(  # noqa: SLF001
            sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 32
        )
        change = GraphChange(
            anchor_upserts=tuple(
                Anchor(f"person-{index}", "person", f"Person {index}") for index in range(50)
            )
        )

        outcome = system.apply_graph_change(
            GraphChangeRequest(GraphChangeTarget.DEFINITION_DELTA, change),
            provenance=OWNER,
        )

        assert outcome.accepted, outcome.findings
        assert system.store.proposal_state().staged_anchor_count == 50
        assert materialize_state(system).graph.objects() == ()
    finally:
        system.close()


def test_prospective_overlay_isolated_queryable_and_activates_atomically(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a", "person", "Ada"),)), provenance=OWNER
        ).accepted
        changed = system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,), type_removals=("person",)),
            provenance=OWNER,
        )
        assert changed.accepted and changed.proposed_definition_identity is not None
        staged = system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("a", "team", "Ada"),)),
            ),
            provenance=OWNER,
        )
        assert staged.accepted

        current = system.query_graph(
            GraphQuery(
                (AnchorGroup("people", ("person",)),),
                RowQueryOutput(
                    kind="rows",
                    projections=(AnchorProjection("person-result", "people"),),
                    maximum_rows=2,
                ),
            )
        )
        prospective = system.query_graph(
            GraphQuery(
                (AnchorGroup("teams", ("team",)),),
                RowQueryOutput(
                    kind="rows",
                    projections=(AnchorProjection("team-result", "teams"),),
                    maximum_rows=2,
                ),
                state=ProspectiveSelection(kind="prospective"),
            )
        )
        assert current.accepted and current.rows[0].anchors[0].anchor.type_key == "person"
        assert prospective.accepted and prospective.rows[0].anchors[0].anchor.type_key == "team"

        assessment = _assess_delta(system)
        assert assessment.accepted and assessment.conforms
        assert assessment.assessment_id is not None
        outcome = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
        )
        assert outcome.accepted
        assert system.definition_delta().proposed_definition_identity is None
        state = materialize_state(system)
        assert state.graph.anchor("a") == Anchor("a", "team", "Ada")
        assert state.active_definitions.anchor_type("team") == TEAM
    finally:
        system.close()


def test_complete_invalid_assessment_is_stored_once_and_paged(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("a", "person", "Ada"),
                    Anchor("b", "person", "Babbage"),
                )
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,), type_removals=("person",)),
            provenance=OWNER,
        ).accepted

        first = _assess_delta(system, maximum=1)
        assert first.accepted and not first.conforms
        assert first.finding_count == 2
        assert first.returned_start_ordinal == 1
        assert len(first.returned_findings) == 1 and first.more_findings
        assert first.assessment_id is not None
        second = system.check(
            ValidationRequest(
                ValidationRequestKind.READ_FINDINGS,
                ValidationScope.DEFINITION_DELTA,
                1,
                assessment_id=first.assessment_id,
                start_ordinal=2,
            )
        )
        assert second.assessment_id == first.assessment_id
        assert second.returned_start_ordinal == 2
        assert len(second.returned_findings) == 1 and not second.more_findings
    finally:
        system.close()


def test_assessment_and_finding_pages_accept_oversized_positive_maxima(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        revision = system.store.current_revision()
        current = system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.GRAPH_CONFORMANCE,
                2**100,
            ),
            provenance=OWNER,
        )
        assert current.accepted and current.conforms and current.returned_findings == ()
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,), type_removals=("person",)),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(
                    anchor_upserts=(
                        Anchor("a", "person", "Ada"),
                        Anchor("b", "person", "Babbage"),
                    )
                ),
            ),
            provenance=OWNER,
        ).accepted
        prospective_revision = system.store.current_revision()

        prospective = _assess_delta(system, maximum=2**100)

        assert prospective.accepted and not prospective.conforms
        assert prospective.finding_count == len(prospective.returned_findings)
        assert prospective.assessment_id is not None
        page = system.check(
            ValidationRequest(
                ValidationRequestKind.READ_FINDINGS,
                ValidationScope.DEFINITION_DELTA,
                2**100,
                assessment_id=prospective.assessment_id,
                start_ordinal=1,
            ),
            provenance=OWNER,
        )
        assert page.accepted
        assert page.returned_findings == prospective.returned_findings
        assert system.store.current_revision() == prospective_revision
        assert prospective_revision > revision
        assert system.store.activity_records()[-1].outcome_category.value == "accepted"
    finally:
        system.close()


def test_activation_rejects_assessment_made_stale_by_proposal_edit(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        clean = _assess_delta(system)
        assert clean.conforms and clean.assessment_id is not None
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("t", "team", "Team"),)),
            ),
            provenance=OWNER,
        ).accepted
        rejected = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(clean.assessment_id), provenance=OWNER
        )
        assert not rejected.accepted
        assert system.definition_delta().proposed_definition_identity is not None
    finally:
        system.close()


def test_prospective_definition_discovery_uses_the_proposed_vocabulary(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,), type_removals=("person",)),
            provenance=OWNER,
        ).accepted
        summary = system.definition_summary(
            DefinitionSummaryRequest(state=ProspectiveSelection(kind="prospective"))
        )
        detail = system.inspect_definitions(
            DefinitionInspectionRequest(
                ("team",),
                state=ProspectiveSelection(kind="prospective"),
            )
        )
        assert [each.type_key for each in summary.anchor_types] == ["team"]
        assert detail.accepted and detail.anchor_details[0].anchor_type == TEAM
    finally:
        system.close()


def test_definition_discovery_never_decodes_the_large_graph_overlay(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(
                    anchor_upserts=tuple(
                        Anchor(f"team-{index}", "team", f"Team {index}") for index in range(2_000)
                    )
                ),
            ),
            provenance=OWNER,
        ).accepted
        system.store.reset_instrumentation()

        summary = system.definition_summary(
            DefinitionSummaryRequest(state=ProspectiveSelection(kind="prospective"))
        )
        detail = system.inspect_definitions(
            DefinitionInspectionRequest(
                ("team",),
                state=ProspectiveSelection(kind="prospective"),
            )
        )

        assert summary.accepted and detail.accepted
        assert system.store.current_graph_object_decodes == 0
    finally:
        system.close()


def test_active_equivalent_graph_edit_does_not_create_an_empty_proposal(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        anchor = Anchor("a", "person", "Ada")
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(anchor,)), provenance=OWNER
        ).accepted
        revision = system.store.current_revision()

        outcome = system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(anchor,)),
            ),
            provenance=OWNER,
        )

        assert outcome.accepted and outcome.resulting_revision is None
        assert system.store.current_revision() == revision
        assert system.definition_delta().proposed_definition_identity is None
    finally:
        system.close()


def test_complete_assessment_counts_valid_multiplicity_once(tmp_path: Path) -> None:
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, AnchorTypeDefinition("project", "A project.")),
        link_types=(
            LinkTypeDefinition(
                "works",
                EndpointConstraint(("person",), ("project",), "Work endpoints."),
                "Work.",
            ),
        ),
        relationship_constraints=(
            LinkMultiplicityConstraint(
                "works", LinkEnd.SOURCE, ("person",), ("project",), 1, 1, "One project."
            ),
        ),
    )
    system = RTGSystem.open(tmp_path / "multiplicity.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=OWNER, initialization_summary="fresh"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("p", "person", "Person"),
                    Anchor("j", "project", "Project"),
                ),
                link_upserts=(Link("w", "works", "p", "j"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted

        report = _assess_delta(system)

        assert report.conforms and report.finding_count == 0
        assert report.assessment_id is not None
        assert system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(report.assessment_id), provenance=OWNER
        ).accepted
        assert system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.GRAPH_CONFORMANCE,
                10,
            )
        ).conforms
    finally:
        system.close()


def test_reassessment_reports_stale_base_until_identity_is_restaged(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a", "person", "Ada"),)), provenance=OWNER
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,), type_removals=("person",)),
            provenance=OWNER,
        ).accepted
        proposed = Anchor("a", "team", "Ada")
        request = GraphChangeRequest(
            GraphChangeTarget.DEFINITION_DELTA,
            GraphChange(anchor_upserts=(proposed,)),
        )
        assert system.apply_graph_change(request, provenance=OWNER).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a", "person", "Ada Lovelace"),)),
            provenance=OWNER,
        ).accepted

        stale = _assess_delta(system)
        assert not stale.conforms
        assert any("stale active base" in each.summary for each in stale.returned_findings)

        assert system.apply_graph_change(request, provenance=OWNER).accepted
        clean = _assess_delta(system)
        assert clean.conforms and clean.assessment_id is not None
        assert system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(clean.assessment_id), provenance=OWNER
        ).accepted
    finally:
        system.close()


def test_stale_proposal_base_does_not_hide_prospective_multiplicity_findings(
    tmp_path: Path,
) -> None:
    subject = AnchorTypeDefinition("subject", "A constrained subject.")
    eligible = AnchorTypeDefinition("eligible", "An eligible opposite.")
    ineligible = AnchorTypeDefinition("ineligible", "An ineligible opposite.")
    edge = LinkTypeDefinition(
        "edge",
        EndpointConstraint(("subject",), ("eligible", "ineligible"), "Endpoints."),
        "An edge.",
    )
    rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("subject",), ("eligible",), 0, 1, "At most one."
    )
    system = RTGSystem.open(tmp_path / "stale-impact-base.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(subject, eligible, ineligible),
                link_types=(edge,),
                relationship_constraints=(rule,),
            ),
            provenance=OWNER,
            initialization_summary="stale impact base",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("subject", "subject", "Subject"),
                    Anchor("opposite", "eligible", "Opposite"),
                ),
                link_upserts=(Link("first", "edge", "subject", "opposite"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("opposite", "eligible", "Staged display"),)),
            ),
            provenance=OWNER,
        ).accepted

        # Current meaning remains conforming: the staged identity becomes ineligible while
        # a new eligible opposite replaces its contribution.
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("opposite", "ineligible", "Current"),
                    Anchor("replacement", "eligible", "Replacement"),
                ),
                link_upserts=(Link("second", "edge", "subject", "replacement"),),
            ),
            provenance=OWNER,
        ).accepted

        assessment = _assess_delta(system)
        summaries = tuple(finding.summary for finding in assessment.returned_findings)
        complete_summaries = {
            finding.summary for finding in _complete_prospective_graph_findings(system)
        }
        assert any("stale active base" in summary for summary in summaries)
        assert any("participates in 2 'edge' links" in summary for summary in summaries)
        assert complete_summaries <= set(summaries)
        key = semantic_identity(relationship_identity(rule))
        assert tuple(
            system.store._connection.execute(  # noqa: SLF001
                "SELECT rule_key, subject_uuid, constrained_end FROM multiplicity_work"
            )
        ) == ((key, "subject", "source"),)
        assert assessment.assessment_id is not None
        assert not system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
        ).accepted
    finally:
        system.close()


def test_stale_proposal_base_does_not_hide_structural_relationship_findings(
    tmp_path: Path,
) -> None:
    first = AnchorTypeDefinition("first", "The original endpoint type.")
    second = AnchorTypeDefinition("second", "The current endpoint type.")
    target = AnchorTypeDefinition("target", "A target.")
    old_edge = LinkTypeDefinition(
        "oldEdge", EndpointConstraint(("first",), ("target",), "Old endpoints."), "Old."
    )
    new_edge = LinkTypeDefinition(
        "newEdge", EndpointConstraint(("second",), ("target",), "New endpoints."), "New."
    )
    system = RTGSystem.open(tmp_path / "stale-structural-base.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(first, second, target), link_types=(old_edge, new_edge)
            ),
            provenance=OWNER,
            initialization_summary="stale structural base",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("endpoint", "first", "Endpoint"),
                    Anchor("target", "target", "Target"),
                ),
                link_upserts=(Link("edge", "oldEdge", "endpoint", "target"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("endpoint", "first", "Staged display"),)),
            ),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(Anchor("endpoint", "second", "Current"),),
                link_upserts=(Link("edge", "newEdge", "endpoint", "target"),),
            ),
            provenance=OWNER,
        ).accepted

        assessment = _assess_delta(system)
        summaries = tuple(finding.summary for finding in assessment.returned_findings)
        complete_summaries = {
            finding.summary for finding in _complete_prospective_graph_findings(system)
        }
        assert any("stale active base" in summary for summary in summaries)
        assert any("endpoint constraint does not permit" in summary for summary in summaries)
        assert complete_summaries <= set(summaries)
        connection = system.store._connection  # noqa: SLF001
        assert tuple(connection.execute("SELECT uuid FROM assessment_structural_relationship")) == (
            ("edge",),
        )
        assert ("edge",) in tuple(connection.execute("SELECT uuid FROM assessment_validation_uuid"))
        assert assessment.assessment_id is not None
        assert not system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
        ).accepted
    finally:
        system.close()


def test_type_upsert_replaces_the_prior_kind_at_shared_natural_identity(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "kind-change.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(AnchorTypeDefinition("base", "Base."),),
                associated_data_types=(
                    AssociatedDataTypeDefinition(
                        "shared", permitted_anchor_type_keys=("base",), description="Old kind."
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("shared", "New kind."),)),
            provenance=OWNER,
        ).accepted
        summary = system.definition_summary(
            DefinitionSummaryRequest(state=ProspectiveSelection(kind="prospective"))
        )
        assessment = _assess_delta(system)
        assert [value.type_key for value in summary.anchor_types] == ["base", "shared"]
        assert assessment.conforms
    finally:
        system.close()


def test_zero_finding_assessment_has_only_the_modeled_first_empty_page(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        clean = _assess_delta(system)
        assert clean.conforms and clean.assessment_id is not None

        rejected = system.check(
            ValidationRequest(
                ValidationRequestKind.READ_FINDINGS,
                ValidationScope.DEFINITION_DELTA,
                1,
                assessment_id=clean.assessment_id,
                start_ordinal=2,
            )
        )
        assert not rejected.accepted
    finally:
        system.close()


def test_one_key_definition_edit_stores_and_decodes_only_that_key(tmp_path: Path) -> None:
    definitions = GraphDefinitionSet(
        anchor_types=tuple(
            AnchorTypeDefinition(f"type-{index}", f"Type {index}.") for index in range(1_000)
        )
    )
    system = RTGSystem.open(tmp_path / "many-definitions.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=OWNER, initialization_summary="fresh"
        ).accepted
        system.store.reset_instrumentation()

        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("type-500", "Updated."),)),
            provenance=OWNER,
        ).accepted

        assert system.store.current_definition_decodes == 1
        connection = system.store._connection  # noqa: SLF001
        assert (
            connection.execute("SELECT count(*) FROM proposal_definition_type").fetchone()[0] == 1
        )
        assert connection.execute("SELECT count(*) FROM definition_type").fetchone()[0] == 1_001
    finally:
        system.close()


def test_one_overlay_edit_does_not_scan_the_staged_population(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(
                    anchor_upserts=tuple(
                        Anchor(f"a-{index}", "person", f"Person {index}") for index in range(2_000)
                    )
                ),
            ),
            provenance=OWNER,
        ).accepted
        statements: list[str] = []
        system.store._connection.set_trace_callback(statements.append)  # noqa: SLF001

        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("a-0", "person", "Updated"),)),
            ),
            provenance=OWNER,
        ).accepted

        normalized = " ".join(statement.lower() for statement in statements)
        assert "from proposal_entry order by" not in normalized
        assert "count(*) from proposal_entry" not in normalized
    finally:
        system.close()


def test_narrow_definition_assessment_does_not_decode_unaffected_graph(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(
                    Anchor(f"person-{index}", "person", f"Person {index}") for index in range(5_000)
                )
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        system.store.reset_instrumentation()

        report = _assess_delta(system)

        assert report.conforms
        assert system.store.current_graph_object_decodes == 0
    finally:
        system.close()


def test_sparse_definition_events_replay_edits_unstaging_discard_and_activation(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        changed_person = AnchorTypeDefinition("person", "Changed.")
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM, changed_person)), provenance=OWNER
        ).accepted
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))

        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(PERSON,)), provenance=OWNER
        ).accepted
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))

        assert system.discard_definition_delta(provenance=OWNER).accepted
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))

        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        assessment = _assess_delta(system)
        assert assessment.conforms and assessment.assessment_id is not None
        assert system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
        ).accepted
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))
    finally:
        system.close()


def test_assessment_closure_catches_staged_link_endpoint_multiplicity(tmp_path: Path) -> None:
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, AnchorTypeDefinition("project", "A project.")),
        link_types=(
            LinkTypeDefinition(
                "works",
                EndpointConstraint(("person",), ("project",), "Work endpoints."),
                "Work.",
            ),
        ),
        relationship_constraints=(
            LinkMultiplicityConstraint(
                "works", LinkEnd.SOURCE, ("person",), ("project",), 0, 1, "At most one."
            ),
        ),
    )
    system = RTGSystem.open(tmp_path / "link-closure.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=OWNER, initialization_summary="fresh"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("p", "person", "Person"),
                    Anchor("j1", "project", "Project 1"),
                    Anchor("j2", "project", "Project 2"),
                ),
                link_upserts=(Link("w1", "works", "p", "j1"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(link_upserts=(Link("w2", "works", "p", "j2"),)),
            ),
            provenance=OWNER,
        ).accepted

        report = _assess_delta(system)

        assert not report.conforms
        assert any("outside 0..1" in finding.summary for finding in report.returned_findings)
    finally:
        system.close()


def test_endpoint_type_change_cannot_activate_an_incomplete_multiplicity_closure(
    tmp_path: Path,
) -> None:
    counted = AnchorTypeDefinition("counted", "A counted target.")
    uncounted = AnchorTypeDefinition("uncounted", "An uncounted target.")
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, counted, uncounted),
        link_types=(
            LinkTypeDefinition(
                "related",
                EndpointConstraint(("person",), ("counted", "uncounted"), "Related endpoints."),
                "A relation.",
            ),
        ),
        relationship_constraints=(
            LinkMultiplicityConstraint(
                "related",
                LinkEnd.SOURCE,
                ("person",),
                ("counted",),
                0,
                1,
                "At most one counted target.",
            ),
        ),
    )
    system = RTGSystem.open(tmp_path / "fixed-point-closure.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=OWNER, initialization_summary="fresh"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("s", "person", "Source"),
                    Anchor("x", "uncounted", "Uncounted"),
                    Anchor("z", "counted", "Counted"),
                ),
                link_upserts=(
                    Link("rel-x", "related", "s", "x"),
                    Link("rel-z", "related", "s", "z"),
                ),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("x", "counted", "Counted now"),)),
            ),
            provenance=OWNER,
        ).accepted
        before = materialize_state(system)
        before_history = system.history(
            HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100)
        ).canonical_entries

        report = _assess_delta(system)

        assert report.accepted and not report.conforms
        assert report.assessment_id is not None
        assert any("outside 0..1" in finding.summary for finding in report.returned_findings)
        activation = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(report.assessment_id), provenance=OWNER
        )
        assert not activation.accepted
        assert semantic_state_equal(materialize_state(system), before)
        assert system.store.current_revision() == before.revision
        after_history = system.history(
            HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100)
        ).canonical_entries
        assert after_history == before_history
    finally:
        system.close()


def test_endpoint_type_change_revalidates_incident_link_without_a_multiplicity_rule(
    tmp_path: Path,
) -> None:
    project = AnchorTypeDefinition("project", "A project.")
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, TEAM, project),
        link_types=(
            LinkTypeDefinition(
                "assigned",
                EndpointConstraint(("person",), ("project",), "Assignment endpoints."),
                "Assignment.",
            ),
        ),
    )
    system = RTGSystem.open(tmp_path / "endpoint-type-local.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=OWNER, initialization_summary="fresh"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("p", "person", "Person"),
                    Anchor("j", "project", "Project"),
                ),
                link_upserts=(Link("assignment", "assigned", "p", "j"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("p", "team", "Team"),)),
            ),
            provenance=OWNER,
        ).accepted

        report = _assess_delta(system)

        assert not report.conforms
        assert any(
            "endpoint constraint does not permit" in item.summary
            for item in report.returned_findings
        )
    finally:
        system.close()


def test_anchor_tombstone_revalidates_links_and_far_multiplicity_subjects(tmp_path: Path) -> None:
    project = AnchorTypeDefinition("project", "A project.")
    system = RTGSystem.open(tmp_path / "anchor-tombstone.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON, project),
                link_types=(
                    LinkTypeDefinition(
                        "assigned",
                        EndpointConstraint(("person",), ("project",), "Assignment endpoints."),
                        "Assignment.",
                    ),
                ),
                relationship_constraints=(
                    LinkMultiplicityConstraint(
                        "assigned",
                        LinkEnd.TARGET,
                        ("project",),
                        ("person",),
                        1,
                        1,
                        "Each project has one person.",
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("p", "person", "Person"),
                    Anchor("j", "project", "Project"),
                ),
                link_upserts=(Link("assignment", "assigned", "p", "j"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_removals=("p",)),
            ),
            provenance=OWNER,
        ).accepted
        before = materialize_state(system)

        report = _assess_delta(system)

        assert not report.conforms
        summaries = {item.summary for item in report.returned_findings}
        assert any("no anchor or associated data" in summary for summary in summaries)
        assert any("outside 1..1" in summary for summary in summaries)
        assert report.assessment_id is not None
        activation = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(report.assessment_id), provenance=OWNER
        )
        assert not activation.accepted
        assert semantic_state_equal(materialize_state(system), before)
    finally:
        system.close()


def test_repeated_anchor_references_have_set_multiplicity_in_prospective_sql(
    tmp_path: Path,
) -> None:
    note = AssociatedDataTypeDefinition(
        "note", permitted_anchor_type_keys=("person",), description="A note."
    )
    for lower, upper, expected_multiplicity_finding in ((0, 1, False), (2, 2, True)):
        base_constraint = DirectAssociationMultiplicityConstraint(
            DirectAssociationEnd.ANCHOR,
            ("person",),
            ("note",),
            0,
            1,
            "Initial set cardinality.",
        )
        proposed_constraint = DirectAssociationMultiplicityConstraint(
            DirectAssociationEnd.ANCHOR,
            ("person",),
            ("note",),
            lower,
            upper,
            "Proposed set cardinality.",
        )
        definitions = GraphDefinitionSet(
            anchor_types=(PERSON,),
            associated_data_types=(note,),
            relationship_constraints=(base_constraint,),
        )
        system = RTGSystem.open(tmp_path / f"association-set-{lower}.sqlite3")
        try:
            assert system.initialize_fresh(
                definitions, provenance=OWNER, initialization_summary="fresh"
            ).accepted
            assert system.apply_graph_change(
                GraphChange(anchor_upserts=(Anchor("a", "person", "Anchor"),)),
                provenance=OWNER,
            ).accepted
            assert system.set_definition_delta(
                DefinitionChange(
                    anchor_type_upserts=(TEAM,),
                    relationship_constraint_upserts=(proposed_constraint,),
                ),
                provenance=OWNER,
            ).accepted
            repeated = AssociatedDataObject("d", "note", ("a", "a"), {})
            assert system.apply_graph_change(
                GraphChangeRequest(
                    GraphChangeTarget.DEFINITION_DELTA,
                    GraphChange(associated_data_upserts=(repeated,)),
                ),
                provenance=OWNER,
            ).accepted

            semantic_findings = assess_object_neighborhood(
                (Anchor("a", "person", "Anchor"), repeated),
                GraphDefinitionSet(
                    anchor_types=(PERSON, TEAM),
                    associated_data_types=(note,),
                    relationship_constraints=(proposed_constraint,),
                ),
            )
            report = _assess_delta(system)

            assert not report.conforms
            assert len(report.returned_findings) == len(semantic_findings)
            multiplicity_findings = [
                finding
                for finding in report.returned_findings
                if "matching direct associations" in finding.summary
            ]
            assert bool(multiplicity_findings) is expected_multiplicity_finding
            assert any("outside" in finding.summary for finding in semantic_findings) is (
                expected_multiplicity_finding
            )
        finally:
            system.close()


def test_assessment_closure_validates_reverse_definition_dependencies(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "definition-closure.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON,),
                associated_data_types=(
                    AssociatedDataTypeDefinition(
                        "note", permitted_anchor_type_keys=("person",), description="A note."
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(type_removals=("person",)), provenance=OWNER
        ).accepted

        report = _assess_delta(system)

        assert not report.conforms
        assert any("unknown anchor type" in finding.summary for finding in report.returned_findings)
        assert not validate_definition_set(materialize_state(system).active_definitions)
    finally:
        system.close()


def test_proposed_and_activated_definition_identity_is_content_canonical(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        staged = system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        )
        assert staged.proposed_definition_identity is not None
        proposed = materialize_definitions(system, prospective=True)
        assert staged.proposed_definition_identity == definition_identity(proposed)

        assessment = _assess_delta(system)
        assert assessment.conforms and assessment.assessment_id is not None
        assert system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
        ).accepted
        active = materialize_definitions(system)
        head_identity = system.store._connection.execute(  # noqa: SLF001
            "SELECT active_definition_set_id FROM state_head WHERE id = 0"
        ).fetchone()[0]
        assert head_identity == definition_identity(active)
    finally:
        system.close()


def test_type_change_closure_revalidates_opposite_multiplicity_participant(tmp_path: Path) -> None:
    project = AnchorTypeDefinition("project", "A project.")
    system = RTGSystem.open(tmp_path / "opposite-closure.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON, TEAM, project),
                link_types=(
                    LinkTypeDefinition(
                        "assigned",
                        EndpointConstraint(
                            ("person", "team"), ("project",), "Assignment endpoints."
                        ),
                        "Assignment.",
                    ),
                ),
                relationship_constraints=(
                    LinkMultiplicityConstraint(
                        "assigned",
                        LinkEnd.TARGET,
                        ("project",),
                        ("person",),
                        1,
                        1,
                        "Each project has one person.",
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("p", "person", "Person"),
                    Anchor("j", "project", "Project"),
                ),
                link_upserts=(Link("assignment", "assigned", "p", "j"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("p", "team", "Team"),)),
            ),
            provenance=OWNER,
        ).accepted

        report = _assess_delta(system)

        assert not report.conforms
        assert any("outside 1..1" in finding.summary for finding in report.returned_findings)
    finally:
        system.close()


def test_changed_multiplicity_is_evaluated_only_by_the_set_based_pass(tmp_path: Path) -> None:
    project = AnchorTypeDefinition("project", "A project.")
    original = LinkMultiplicityConstraint(
        "works", LinkEnd.SOURCE, ("person",), ("project",), 0, 1, "Optional project."
    )
    required = LinkMultiplicityConstraint(
        "works", LinkEnd.SOURCE, ("person",), ("project",), 1, 1, "Required project."
    )
    system = RTGSystem.open(tmp_path / "relationship-pass.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON, project),
                link_types=(
                    LinkTypeDefinition(
                        "works",
                        EndpointConstraint(("person",), ("project",), "Work endpoints."),
                        "Work.",
                    ),
                ),
                relationship_constraints=(original,),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("p", "person", "Person"),
                    Anchor("j", "project", "Project"),
                ),
                link_upserts=(Link("w", "works", "p", "j"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(relationship_constraint_upserts=(required,)), provenance=OWNER
        ).accepted

        report = _assess_delta(system)

        assert report.conforms and report.finding_count == 0
    finally:
        system.close()


def test_description_only_definition_edit_does_not_visit_its_graph_population(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(
                    Anchor(f"person-{index}", "person", f"Person {index}") for index in range(5_000)
                )
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(
                anchor_type_upserts=(AnchorTypeDefinition("person", "Updated words only."),)
            ),
            provenance=OWNER,
        ).accepted
        loaded: list[int] = []
        original = system.store._load_object_value  # noqa: SLF001

        def observed(value_id: int):
            loaded.append(value_id)
            return original(value_id)

        system.store._load_object_value = observed  # type: ignore[method-assign]  # noqa: SLF001

        report = _assess_delta(system)

        assert report.conforms
        assert loaded == []
    finally:
        system.close()


def test_one_object_proposal_assessment_visits_only_its_neighborhood(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(
                    Anchor(f"person-{index}", "person", f"Person {index}") for index in range(2_000)
                )
            ),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("person-0", "person", "Updated"),)),
            ),
            provenance=OWNER,
        ).accepted
        loaded: list[int] = []
        original = system.store._load_object_value  # noqa: SLF001

        def observed(value_id: int):
            loaded.append(value_id)
            return original(value_id)

        system.store._load_object_value = observed  # type: ignore[method-assign]  # noqa: SLF001

        report = _assess_delta(system)

        assert report.conforms
        assert loaded == []
    finally:
        system.close()


def test_description_only_multiplicity_edit_visits_no_graph_objects(tmp_path: Path) -> None:
    original = LinkMultiplicityConstraint(
        "works", LinkEnd.SOURCE, ("person",), ("person",), 0, 1, "Original words."
    )
    renamed = LinkMultiplicityConstraint(
        "works", LinkEnd.SOURCE, ("person",), ("person",), 0, 1, "New words."
    )
    system = RTGSystem.open(tmp_path / "rule-description.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON,),
                link_types=(
                    LinkTypeDefinition(
                        "works",
                        EndpointConstraint(("person",), ("person",), "Endpoints."),
                        "Work.",
                    ),
                ),
                relationship_constraints=(original,),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(
                    Anchor(f"person-{index}", "person", f"Person {index}") for index in range(2_000)
                )
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(relationship_constraint_upserts=(renamed,)), provenance=OWNER
        ).accepted
        loaded: list[int] = []
        original_loader = system.store._load_object_value  # noqa: SLF001

        def observed(value_id: int):
            loaded.append(value_id)
            return original_loader(value_id)

        system.store._load_object_value = observed  # type: ignore[method-assign]  # noqa: SLF001

        report = _assess_delta(system)

        assert report.conforms
        assert loaded == []
    finally:
        system.close()


def test_graph_overlay_replay_is_independent_of_edit_order(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("b", "person", "B"),)),
            ),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("a", "person", "A"),)),
            ),
            provenance=OWNER,
        ).accepted

        assert semantic_state_equal(materialize_state(system), materialize_replay(system))
    finally:
        system.close()


def test_graph_overlay_semantic_equality_ignores_request_order() -> None:
    left = DefinitionDelta(
        GraphDefinitionSet(anchor_types=(PERSON,)),
        GraphChange(anchor_upserts=(Anchor("a", "person", "A"), Anchor("b", "person", "B"))),
    )
    right = DefinitionDelta(
        GraphDefinitionSet(anchor_types=(PERSON,)),
        GraphChange(anchor_upserts=(Anchor("b", "person", "B"), Anchor("a", "person", "A"))),
    )

    assert definition_delta_equal(left, right)


def test_graph_overlay_semantic_equality_preserves_json_kinds() -> None:
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                "value", permitted_anchor_type_keys=("person",), description="A value."
            ),
        ),
    )
    boolean = DefinitionDelta(
        definitions,
        GraphChange(associated_data_upserts=(AssociatedDataObject("v", "value", (), {"x": True}),)),
    )
    number = DefinitionDelta(
        definitions,
        GraphChange(
            associated_data_upserts=(AssociatedDataObject("v", "value", (), {"x": Decimal(1)}),)
        ),
    )

    assert not definition_delta_equal(boolean, number)


def test_check_pages_and_rejections_are_observed_under_the_requested_scope(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        before = system.store.activity_record_count()
        report = system.check(
            ValidationRequest(
                ValidationRequestKind.READ_FINDINGS,
                ValidationScope.DEFINITION_DELTA,
                10,
                assessment_id="unknown",
                start_ordinal=1,
            ),
            provenance=OWNER,
        )
        records = system.store.activity_records()

        assert not report.accepted
        assert system.store.activity_record_count() == before + 1
        assert (
            records[-1].semantic_scope == "the prospective graph against its proposed definitions"
        )
    finally:
        system.close()


def test_w004_transactions_roll_back_every_projection_family(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        connection = system.store._connection  # noqa: SLF001
        revision = system.store.current_revision()
        connection.execute(
            "CREATE TRIGGER fail_proposal BEFORE INSERT ON canonical_record"
            " WHEN NEW.record_kind = 'definitionDeltaChange'"
            " BEGIN SELECT RAISE(ABORT, 'proposal fault'); END"
        )
        failed = system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("a", "person", "A"),)),
            ),
            provenance=OWNER,
        )
        assert not failed.accepted
        assert system.store.current_revision() == revision
        assert system.definition_delta().proposed_definition_identity is None
        connection.execute("DROP TRIGGER fail_proposal")

        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        connection.execute(
            "CREATE TRIGGER fail_assessment BEFORE INSERT ON current_assessment"
            " BEGIN SELECT RAISE(ABORT, 'assessment fault'); END"
        )
        failed_assessment = _assess_delta(system)
        assert not failed_assessment.accepted
        assert connection.execute("SELECT count(*) FROM validation_assessment").fetchone()[0] == 0
        connection.execute("DROP TRIGGER fail_assessment")

        clean = _assess_delta(system)
        assert clean.conforms and clean.assessment_id is not None
        revision = system.store.current_revision()
        connection.execute(
            "CREATE TRIGGER fail_activation BEFORE UPDATE OF active_definition_set_id"
            " ON state_head BEGIN SELECT RAISE(ABORT, 'activation fault'); END"
        )
        failed_activation = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(clean.assessment_id), provenance=OWNER
        )
        assert not failed_activation.accepted
        assert system.store.current_revision() == revision
        assert system.definition_delta().proposed_definition_identity is not None
    finally:
        system.close()


def test_active_and_prospective_share_exact_opposite_membership_work(tmp_path: Path) -> None:
    subject = AnchorTypeDefinition("subject", "A constrained subject.")
    eligible = AnchorTypeDefinition("eligible", "An eligible opposite.")
    ineligible = AnchorTypeDefinition("ineligible", "An ineligible opposite.")
    edge = LinkTypeDefinition(
        "edge",
        EndpointConstraint(("subject",), ("eligible", "ineligible"), "Endpoints."),
        "An edge.",
    )
    rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("subject",), ("eligible",), 0, None, "Eligible edges."
    )
    system = RTGSystem.open(tmp_path / "exact-impact.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(subject, eligible, ineligible),
                link_types=(edge,),
                relationship_constraints=(rule,),
            ),
            provenance=OWNER,
            initialization_summary="exact impact",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("subject", "subject", "Subject"),
                    Anchor("opposite", "eligible", "Opposite"),
                ),
                link_upserts=(Link("edge", "edge", "subject", "opposite"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        change = GraphChange(anchor_upserts=(Anchor("opposite", "ineligible", "Opposite"),))
        connection = system.store._connection  # noqa: SLF001
        proposal_before = tuple(connection.execute("SELECT * FROM proposal_entry ORDER BY uuid"))

        connection.execute("BEGIN")
        system.store._prepare_active_graph_change_unlocked(change)  # noqa: SLF001
        active_reasons = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )
        active_work = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end"
                " FROM multiplicity_work ORDER BY 1, 2, 3"
            )
        )
        assert tuple(connection.execute("SELECT * FROM proposal_entry ORDER BY uuid")) == (
            proposal_before
        )
        connection.execute("ROLLBACK")

        proposal_identity = system.definition_delta().proposed_definition_identity
        overlay_identity = system.definition_delta().graph_overlay_identity
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("new", "subject", "New"),)),
            provenance=OWNER,
        ).accepted
        assert system.definition_delta().proposed_definition_identity == proposal_identity
        assert system.definition_delta().graph_overlay_identity == overlay_identity

        assert system.apply_graph_change(
            GraphChangeRequest(GraphChangeTarget.DEFINITION_DELTA, change), provenance=OWNER
        ).accepted
        assert _assess_delta(system).conforms
        prospective_reasons = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )
        prospective_work = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end"
                " FROM multiplicity_work ORDER BY 1, 2, 3"
            )
        )
        expected_key = semantic_identity(relationship_identity(rule))

        assert (
            active_reasons
            == prospective_reasons
            == ((expected_key, "subject", "source", "oppositeMembershipChanged"),)
        )
        assert active_work == prospective_work == ((expected_key, "subject", "source"),)
    finally:
        system.close()


@pytest.mark.parametrize("removal", (False, True))
def test_active_and_prospective_share_exact_relationship_membership_work(
    tmp_path: Path, removal: bool
) -> None:
    subject = AnchorTypeDefinition("subject", "A constrained subject.")
    opposite = AnchorTypeDefinition("opposite", "An opposite.")
    edge = LinkTypeDefinition(
        "edge", EndpointConstraint(("subject",), ("opposite",), "Endpoints."), "An edge."
    )
    rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("subject",), ("opposite",), 0, None, "Edges."
    )
    system = RTGSystem.open(tmp_path / f"relationship-impact-{removal}.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(subject, opposite),
                link_types=(edge,),
                relationship_constraints=(rule,),
            ),
            provenance=OWNER,
            initialization_summary="relationship impact",
        ).accepted
        initial_link = (Link("edge", "edge", "subject", "opposite"),) if removal else ()
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("subject", "subject", "Subject"),
                    Anchor("opposite", "opposite", "Opposite"),
                ),
                link_upserts=initial_link,
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        change = (
            GraphChange(link_removals=("edge",))
            if removal
            else GraphChange(link_upserts=(Link("edge", "edge", "subject", "opposite"),))
        )
        connection = system.store._connection  # noqa: SLF001
        connection.execute("BEGIN")
        system.store._prepare_active_graph_change_unlocked(change)  # noqa: SLF001
        active = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )
        connection.execute("ROLLBACK")

        assert system.apply_graph_change(
            GraphChangeRequest(GraphChangeTarget.DEFINITION_DELTA, change), provenance=OWNER
        ).accepted
        assert _assess_delta(system).conforms
        prospective = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )
        key = semantic_identity(relationship_identity(rule))
        assert (
            active == prospective == ((key, "subject", "source", "relationshipMembershipChanged"),)
        )
    finally:
        system.close()


def test_active_and_prospective_share_exact_subject_membership_work(tmp_path: Path) -> None:
    subject = AnchorTypeDefinition("subject", "A constrained subject.")
    other = AnchorTypeDefinition("other", "Another endpoint type.")
    opposite = AnchorTypeDefinition("opposite", "An opposite.")
    edge = LinkTypeDefinition(
        "edge", EndpointConstraint(("subject", "other"), ("opposite",), "Endpoints."), "Edge."
    )
    rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("subject",), ("opposite",), 0, None, "Edges."
    )
    system = RTGSystem.open(tmp_path / "subject-membership-impact.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(subject, other, opposite),
                link_types=(edge,),
                relationship_constraints=(rule,),
            ),
            provenance=OWNER,
            initialization_summary="subject membership",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("subject", "subject", "Subject"),)),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        change = GraphChange(anchor_upserts=(Anchor("subject", "other", "Subject"),))
        connection = system.store._connection  # noqa: SLF001
        connection.execute("BEGIN")
        system.store._prepare_active_graph_change_unlocked(change)  # noqa: SLF001
        active = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )
        connection.execute("ROLLBACK")

        assert system.apply_graph_change(
            GraphChangeRequest(GraphChangeTarget.DEFINITION_DELTA, change), provenance=OWNER
        ).accepted
        assert _assess_delta(system).conforms
        prospective = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )
        key = semantic_identity(relationship_identity(rule))
        assert active == prospective == ((key, "subject", "source", "subjectMembershipChanged"),)
    finally:
        system.close()


@pytest.mark.parametrize(
    "constrained_end", (DirectAssociationEnd.ANCHOR, DirectAssociationEnd.ASSOCIATED_DATA)
)
def test_active_and_prospective_share_direct_association_opposite_membership_work(
    tmp_path: Path, constrained_end: DirectAssociationEnd
) -> None:
    eligible_anchor = AnchorTypeDefinition("eligibleAnchor", "An eligible anchor.")
    outside_anchor = AnchorTypeDefinition("outsideAnchor", "Another anchor.")
    eligible_data = AssociatedDataTypeDefinition(
        "eligibleData", ("eligibleAnchor", "outsideAnchor"), description="Eligible data."
    )
    outside_data = AssociatedDataTypeDefinition(
        "outsideData", ("eligibleAnchor", "outsideAnchor"), description="Other data."
    )
    rule = DirectAssociationMultiplicityConstraint(
        constrained_end,
        ("eligibleAnchor",),
        ("eligibleData",),
        0,
        None,
        "Eligible associations.",
    )
    system = RTGSystem.open(tmp_path / f"direct-opposite-{constrained_end.value}.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(eligible_anchor, outside_anchor),
                associated_data_types=(eligible_data, outside_data),
                relationship_constraints=(rule,),
            ),
            provenance=OWNER,
            initialization_summary="direct opposite membership",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(Anchor("anchor", "eligibleAnchor", "Anchor"),),
                associated_data_upserts=(
                    AssociatedDataObject("data", "eligibleData", ("anchor",), {}),
                ),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
        ).accepted
        change = (
            GraphChange(
                associated_data_upserts=(
                    AssociatedDataObject("data", "outsideData", ("anchor",), {}),
                )
            )
            if constrained_end is DirectAssociationEnd.ANCHOR
            else GraphChange(anchor_upserts=(Anchor("anchor", "outsideAnchor", "Anchor"),))
        )
        connection = system.store._connection  # noqa: SLF001
        connection.execute("BEGIN")
        system.store._prepare_active_graph_change_unlocked(change)  # noqa: SLF001
        active = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )
        connection.execute("ROLLBACK")

        assert system.apply_graph_change(
            GraphChangeRequest(GraphChangeTarget.DEFINITION_DELTA, change), provenance=OWNER
        ).accepted
        assert _assess_delta(system).conforms
        prospective = tuple(
            connection.execute(
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )
        key = semantic_identity(relationship_identity(rule))
        subject_uuid = "anchor" if constrained_end is DirectAssociationEnd.ANCHOR else "data"
        assert (
            active
            == prospective
            == ((key, subject_uuid, constrained_end.value, "oppositeMembershipChanged"),)
        )
    finally:
        system.close()


def test_accepted_incremental_mutations_agree_with_complete_conformance(
    tmp_path: Path,
) -> None:
    subject = AnchorTypeDefinition("subject", "A constrained subject.")
    eligible = AnchorTypeDefinition("eligible", "An eligible opposite.")
    ineligible = AnchorTypeDefinition("ineligible", "An ineligible opposite.")
    link_types = tuple(
        LinkTypeDefinition(
            f"edge-{index}",
            EndpointConstraint(("subject",), ("eligible", "ineligible"), "Endpoints."),
            "An edge.",
        )
        for index in range(2)
    )
    rules = tuple(
        LinkMultiplicityConstraint(
            value.type_key,
            LinkEnd.SOURCE,
            ("subject",),
            ("eligible",),
            0,
            1,
            "At most one eligible opposite.",
        )
        for value in link_types
    )
    system = RTGSystem.open(tmp_path / "incremental-complete-differential.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(subject, eligible, ineligible),
                link_types=link_types,
                relationship_constraints=rules,
            ),
            provenance=OWNER,
            initialization_summary="incremental complete differential",
        ).accepted
        subjects = ("subject-0", "subject-1")
        opposites = ("opposite-0", "opposite-1", "opposite-2")
        opposite_types: dict[str, str] = dict.fromkeys(opposites, "eligible")
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(Anchor(uuid, "subject", uuid) for uuid in subjects)
                + tuple(Anchor(uuid, "eligible", uuid) for uuid in opposites)
            ),
            provenance=OWNER,
        ).accepted

        rng = random.Random(20260819)
        present_links: set[str] = set()
        rejection_count = 0
        for _ in range(120):
            if rng.randrange(4):
                link_type = rng.choice(link_types).type_key
                source = rng.choice(subjects)
                target = rng.choice(opposites)
                uuid = f"{link_type}:{source}:{target}"
                if uuid in present_links:
                    change = GraphChange(link_removals=(uuid,))
                else:
                    change = GraphChange(link_upserts=(Link(uuid, link_type, source, target),))
            else:
                target = rng.choice(opposites)
                next_type = "ineligible" if opposite_types[target] == "eligible" else "eligible"
                change = GraphChange(anchor_upserts=(Anchor(target, next_type, target),))

            outcome = system.apply_graph_change(change, provenance=OWNER)
            if outcome.accepted:
                if change.link_removals:
                    present_links.remove(change.link_removals[0])
                elif change.link_upserts:
                    present_links.add(change.link_upserts[0].uuid)
                elif change.anchor_upserts:
                    value = change.anchor_upserts[0]
                    opposite_types[value.uuid] = value.type_key
                complete = system.check(
                    ValidationRequest(
                        ValidationRequestKind.ASSESS,
                        ValidationScope.GRAPH_CONFORMANCE,
                        100,
                    )
                )
                assert complete.conforms, complete.returned_findings
            else:
                rejection_count += 1
        assert rejection_count >= 10
    finally:
        system.close()


def test_rule_meaning_change_enqueues_only_that_rules_applicable_subjects(tmp_path: Path) -> None:
    subject = AnchorTypeDefinition("subject", "A subject.")
    unrelated = AnchorTypeDefinition("unrelated", "An unrelated anchor.")
    opposite = AnchorTypeDefinition("opposite", "An opposite.")
    edge = LinkTypeDefinition(
        "edge", EndpointConstraint(("subject",), ("opposite",), "Endpoints."), "An edge."
    )
    old_rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("subject",), ("opposite",), 0, 2, "At most two."
    )
    new_rule = LinkMultiplicityConstraint(
        "edge", LinkEnd.SOURCE, ("subject",), ("opposite",), 0, 1, "At most one."
    )
    system = RTGSystem.open(tmp_path / "rule-meaning-impact.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(subject, unrelated, opposite),
                link_types=(edge,),
                relationship_constraints=(old_rule,),
            ),
            provenance=OWNER,
            initialization_summary="rule meaning",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("first", "subject", "First"),
                    Anchor("second", "subject", "Second"),
                    Anchor("other", "unrelated", "Other"),
                )
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(relationship_constraint_upserts=(new_rule,)), provenance=OWNER
        ).accepted

        assert _assess_delta(system).conforms
        key = semantic_identity(relationship_identity(new_rule))
        reasons = tuple(
            system.store._connection.execute(  # noqa: SLF001
                "SELECT rule_key, subject_uuid, constrained_end, reason_kind"
                " FROM multiplicity_impact_reason ORDER BY 1, 2, 3, 4"
            )
        )

        assert reasons == (
            (key, "first", "source", "ruleMeaningChanged"),
            (key, "second", "source", "ruleMeaningChanged"),
        )
    finally:
        system.close()


def test_narrow_assessment_sql_steps_ignore_unrelated_link_population(tmp_path: Path) -> None:
    project = AnchorTypeDefinition("project", "A project.")
    system = RTGSystem.open(tmp_path / "bounded-assessment.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON, project),
                link_types=(
                    LinkTypeDefinition(
                        "works",
                        EndpointConstraint(("person",), ("project",), "Work endpoints."),
                        "Work.",
                    ),
                ),
                relationship_constraints=(
                    LinkMultiplicityConstraint(
                        "works",
                        LinkEnd.SOURCE,
                        ("person",),
                        ("project",),
                        0,
                        2,
                        "At most two.",
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        anchors = [
            Anchor("focus-person", "person", "Focus"),
            Anchor("focus-project", "project", "Focus"),
        ]
        links = [Link("focus-link", "works", "focus-person", "focus-project")]
        for index in range(1_000):
            anchors.extend(
                (
                    Anchor(f"person-{index}", "person", "Unrelated"),
                    Anchor(f"project-{index}", "project", "Unrelated"),
                )
            )
            links.append(Link(f"link-{index}", "works", f"person-{index}", f"project-{index}"))
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=tuple(anchors), link_upserts=tuple(links)),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("focus-person", "person", "Updated focus"),)),
            ),
            provenance=OWNER,
        ).accepted
        steps = 0

        def progress() -> int:
            nonlocal steps
            steps += 100
            return 0

        system.store._connection.set_progress_handler(progress, 100)  # noqa: SLF001
        report = _assess_delta(system)
        system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001

        assert report.conforms
        assert steps < 2_000
    finally:
        system.close()


def test_display_only_assessment_work_ignores_connected_component_length(
    tmp_path: Path,
) -> None:
    def measured(length: int) -> int:
        system = RTGSystem.open(tmp_path / f"connected-{length}.sqlite3")
        try:
            assert system.initialize_fresh(
                GraphDefinitionSet(
                    anchor_types=(PERSON,),
                    link_types=(
                        LinkTypeDefinition(
                            "next",
                            EndpointConstraint(("person",), ("person",), "Chain endpoints."),
                            "A chain edge.",
                        ),
                    ),
                    relationship_constraints=(
                        LinkMultiplicityConstraint(
                            "next",
                            LinkEnd.SOURCE,
                            ("person",),
                            ("person",),
                            0,
                            1,
                            "At most one next edge.",
                        ),
                    ),
                ),
                provenance=OWNER,
                initialization_summary="connected",
            ).accepted
            assert system.apply_graph_change(
                GraphChange(
                    anchor_upserts=tuple(
                        Anchor(f"person-{index}", "person", f"Person {index}")
                        for index in range(length + 1)
                    ),
                    link_upserts=tuple(
                        Link(
                            f"next-{index}",
                            "next",
                            f"person-{index}",
                            f"person-{index + 1}",
                        )
                        for index in range(length)
                    ),
                ),
                provenance=OWNER,
            ).accepted
            assert system.apply_graph_change(
                GraphChangeRequest(
                    GraphChangeTarget.DEFINITION_DELTA,
                    GraphChange(anchor_upserts=(Anchor("person-0", "person", "Renamed person"),)),
                ),
                provenance=OWNER,
            ).accepted
            steps = 0

            def progress() -> int:
                nonlocal steps
                steps += 100
                return 0

            system.store._connection.set_progress_handler(progress, 100)  # noqa: SLF001
            report = _assess_delta(system)
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001
            assert report.conforms
            return steps
        finally:
            system.close()

    short = measured(10)
    long = measured(1_000)

    assert long <= short + 300


def test_link_shape_assessment_scales_with_hub_degree_not_second_hop_degree(
    tmp_path: Path,
) -> None:
    def measured(degree: int) -> int:
        node = AnchorTypeDefinition("node", "A node.")
        edge = LinkTypeDefinition(
            "edge",
            EndpointConstraint(("node",), ("node",), "Edge endpoints."),
            "An edge.",
        )
        rule = LinkMultiplicityConstraint(
            "edge",
            LinkEnd.SOURCE,
            ("node",),
            ("node",),
            0,
            None,
            "Any number of outgoing edges.",
        )
        system = RTGSystem.open(tmp_path / f"hub-comb-{degree}.sqlite3")
        try:
            assert system.initialize_fresh(
                GraphDefinitionSet(
                    anchor_types=(node,),
                    link_types=(edge,),
                    relationship_constraints=(rule,),
                ),
                provenance=OWNER,
                initialization_summary="hub comb",
            ).accepted
            anchors = [Anchor("hub", "node", "Hub"), Anchor("extra", "node", "Extra")]
            links: list[Link] = []
            for spoke in range(degree):
                anchors.append(Anchor(f"spoke-{spoke}", "node", f"Spoke {spoke}"))
                links.append(Link(f"hub-{spoke}", "edge", "hub", f"spoke-{spoke}"))
                for leaf in range(degree):
                    anchors.append(Anchor(f"leaf-{spoke}-{leaf}", "node", f"Leaf {spoke}-{leaf}"))
                    links.append(
                        Link(
                            f"to-leaf-{spoke}-{leaf}",
                            "edge",
                            f"spoke-{spoke}",
                            f"leaf-{spoke}-{leaf}",
                        )
                    )
            assert system.apply_graph_change(
                GraphChange(anchor_upserts=tuple(anchors), link_upserts=tuple(links)),
                provenance=OWNER,
            ).accepted
            assert system.set_definition_delta(
                DefinitionChange(anchor_type_upserts=(TEAM,)), provenance=OWNER
            ).accepted
            assert system.apply_graph_change(
                GraphChangeRequest(
                    GraphChangeTarget.DEFINITION_DELTA,
                    GraphChange(link_upserts=(Link("new-edge", "edge", "hub", "extra"),)),
                ),
                provenance=OWNER,
            ).accepted
            steps = 0

            def progress() -> int:
                nonlocal steps
                steps += 100
                return 0

            system.store._connection.set_progress_handler(progress, 100)  # noqa: SLF001
            report = _assess_delta(system)
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001

            assert report.conforms, report.returned_findings
            return steps
        finally:
            system.close()

    medium_steps = measured(20)
    large_steps = measured(40)

    # Doubling the changed hub degree must not visit every edge of every sibling hub.
    assert large_steps < medium_steps * 3


def test_participant_type_change_scales_with_its_applicable_incident_degree(
    tmp_path: Path,
) -> None:
    def measured(degree: int) -> int:
        central = AnchorTypeDefinition("central", "A central node.")
        other = AnchorTypeDefinition("other", "Another node.")
        spoke = AnchorTypeDefinition("spoke", "A spoke node.")
        leaf = AnchorTypeDefinition("leaf", "A leaf node.")
        edge = LinkTypeDefinition(
            "edge",
            EndpointConstraint(("central", "other", "spoke"), ("spoke", "leaf"), "Edge endpoints."),
            "An edge.",
        )
        rule = LinkMultiplicityConstraint(
            "edge", LinkEnd.SOURCE, ("central",), ("spoke",), 0, None, "Central edges."
        )
        system = RTGSystem.open(tmp_path / f"type-hub-comb-{degree}.sqlite3")
        try:
            assert system.initialize_fresh(
                GraphDefinitionSet(
                    anchor_types=(central, other, spoke, leaf),
                    link_types=(edge,),
                    relationship_constraints=(rule,),
                ),
                provenance=OWNER,
                initialization_summary="type hub comb",
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
                        Link(
                            f"leaf-edge-{spoke_index}-{leaf_index}",
                            "edge",
                            spoke_uuid,
                            leaf_uuid,
                        )
                    )
            assert system.apply_graph_change(
                GraphChange(anchor_upserts=tuple(anchors), link_upserts=tuple(links)),
                provenance=OWNER,
            ).accepted
            assert system.apply_graph_change(
                GraphChangeRequest(
                    GraphChangeTarget.DEFINITION_DELTA,
                    GraphChange(anchor_upserts=(Anchor("hub", "other", "Hub"),)),
                ),
                provenance=OWNER,
            ).accepted
            steps = 0

            def progress() -> int:
                nonlocal steps
                steps += 100
                return 0

            system.store._connection.set_progress_handler(progress, 100)  # noqa: SLF001
            report = _assess_delta(system)
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001
            assert report.conforms, report.returned_findings
            return steps
        finally:
            system.close()

    medium_steps = measured(20)
    large_steps = measured(40)

    assert large_steps < medium_steps * 3


def test_state_wide_rule_cutover_has_linear_sql_step_growth(tmp_path: Path) -> None:
    def measured(population: int) -> int:
        node = AnchorTypeDefinition("node", "A node.")
        edge = LinkTypeDefinition(
            "edge",
            EndpointConstraint(("node",), ("node",), "Edge endpoints."),
            "An edge.",
        )
        current_rule = LinkMultiplicityConstraint(
            "edge", LinkEnd.SOURCE, ("node",), ("node",), 0, 2, "At most two."
        )
        proposed_rule = LinkMultiplicityConstraint(
            "edge", LinkEnd.SOURCE, ("node",), ("node",), 0, 1, "At most one."
        )
        system = RTGSystem.open(tmp_path / f"rule-cutover-{population}.sqlite3")
        try:
            assert system.initialize_fresh(
                GraphDefinitionSet(
                    anchor_types=(node,),
                    link_types=(edge,),
                    relationship_constraints=(current_rule,),
                ),
                provenance=OWNER,
                initialization_summary="rule cutover",
            ).accepted
            anchors = tuple(
                Anchor(f"node-{index}", "node", f"Node {index}") for index in range(population * 2)
            )
            links = tuple(
                Link(f"edge-{index}", "edge", f"node-{index}", f"node-{population + index}")
                for index in range(population)
            )
            assert system.apply_graph_change(
                GraphChange(anchor_upserts=anchors, link_upserts=links), provenance=OWNER
            ).accepted
            assert system.set_definition_delta(
                DefinitionChange(relationship_constraint_upserts=(proposed_rule,)),
                provenance=OWNER,
            ).accepted
            steps = 0

            def progress() -> int:
                nonlocal steps
                steps += 100
                return 0

            system.store._connection.set_progress_handler(progress, 100)  # noqa: SLF001
            report = _assess_delta(system, maximum=population * 2)
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001

            assert report.conforms, report.returned_findings
            return steps
        finally:
            system.close()

    small_steps = measured(100)
    large_steps = measured(500)

    assert large_steps < small_steps * 7


def test_changed_relation_type_includes_unchanged_referenced_objects(tmp_path: Path) -> None:
    other = AnchorTypeDefinition("other", "Another anchor.")
    original_data = AssociatedDataTypeDefinition(
        "note", permitted_anchor_type_keys=("person",), description="A note."
    )
    widened_data = AssociatedDataTypeDefinition(
        "note", permitted_anchor_type_keys=("person", "other"), description="A note."
    )
    original_link = LinkTypeDefinition(
        "related",
        EndpointConstraint(("note",), ("person",), "Original endpoints."),
        "A relation.",
    )
    widened_link = LinkTypeDefinition(
        "related",
        EndpointConstraint(("note", "other"), ("person", "other"), "Wider endpoints."),
        "A relation.",
    )
    system = RTGSystem.open(tmp_path / "changed-relation-type.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON, other),
                associated_data_types=(original_data,),
                link_types=(original_link,),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(Anchor("p", "person", "Person"),),
                associated_data_upserts=(AssociatedDataObject("n", "note", ("p",), {}),),
                link_upserts=(Link("r", "related", "n", "p"),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(
                associated_data_type_upserts=(widened_data,),
                link_type_upserts=(widened_link,),
            ),
            provenance=OWNER,
        ).accepted

        report = _assess_delta(system)

        assert report.conforms and report.finding_count == 0
    finally:
        system.close()


def test_invalid_sparse_rule_is_validated_once_not_per_unrelated_type(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        invalid = LinkMultiplicityConstraint(
            "unknown-link",
            LinkEnd.SOURCE,
            ("unknown-source",),
            ("unknown-target",),
            0,
            1,
            "Invalid while staged.",
        )
        assert system.set_definition_delta(
            DefinitionChange(relationship_constraint_upserts=(invalid,)), provenance=OWNER
        ).accepted

        report = _assess_delta(system, maximum=10)

        assert not report.conforms
        assert report.finding_count == 3
        assert len(report.returned_findings) == 3
    finally:
        system.close()


def test_restaging_identical_overlay_after_active_change_is_a_semantic_no_op(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a", "person", "One"),)), provenance=OWNER
        ).accepted
        request = GraphChangeRequest(
            GraphChangeTarget.DEFINITION_DELTA,
            GraphChange(anchor_upserts=(Anchor("a", "person", "Two"),)),
        )
        assert system.apply_graph_change(request, provenance=OWNER).accepted
        overlay = system.definition_delta().graph_overlay_identity
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a", "person", "Three"),)), provenance=OWNER
        ).accepted
        revision = system.store.current_revision()

        outcome = system.apply_graph_change(request, provenance=OWNER)

        assert outcome.accepted and outcome.resulting_revision is None
        assert system.store.current_revision() == revision
        assert system.definition_delta().graph_overlay_identity == overlay
    finally:
        system.close()


def test_staged_data_assessment_includes_direct_association_multiplicity(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "direct-association.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON,),
                associated_data_types=(
                    AssociatedDataTypeDefinition(
                        "note", permitted_anchor_type_keys=("person",), description="A note."
                    ),
                ),
                relationship_constraints=(
                    DirectAssociationMultiplicityConstraint(
                        DirectAssociationEnd.ASSOCIATED_DATA,
                        ("person",),
                        ("note",),
                        1,
                        1,
                        "One grounding anchor.",
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(associated_data_upserts=(AssociatedDataObject("d", "note", (), {}),)),
            ),
            provenance=OWNER,
        ).accepted

        report = _assess_delta(system)

        assert report.finding_count == 2
        assert any("outside 1..1" in finding.summary for finding in report.returned_findings)
    finally:
        system.close()


def test_anchor_tombstone_revalidates_direct_association_and_data_multiplicity(
    tmp_path: Path,
) -> None:
    system = RTGSystem.open(tmp_path / "direct-association-tombstone.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON,),
                associated_data_types=(
                    AssociatedDataTypeDefinition(
                        "note", permitted_anchor_type_keys=("person",), description="A note."
                    ),
                ),
                relationship_constraints=(
                    DirectAssociationMultiplicityConstraint(
                        DirectAssociationEnd.ASSOCIATED_DATA,
                        ("person",),
                        ("note",),
                        1,
                        1,
                        "One grounding anchor.",
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(Anchor("p", "person", "Person"),),
                associated_data_upserts=(AssociatedDataObject("d", "note", ("p",), {}),),
            ),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_removals=("p",)),
            ),
            provenance=OWNER,
        ).accepted

        report = _assess_delta(system)

        assert not report.conforms
        summaries = {finding.summary for finding in report.returned_findings}
        assert any("no anchor owned by this graph" in summary for summary in summaries)
        assert any("outside 1..1" in summary for summary in summaries)
    finally:
        system.close()


def test_restaging_rejects_cross_kind_active_conflict(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "cross-kind-restage.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(PERSON,),
                associated_data_types=(
                    AssociatedDataTypeDefinition(
                        "note", permitted_anchor_type_keys=("person",), description="A note."
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="fresh",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("h", "person", "Home"),)), provenance=OWNER
        ).accepted
        request = GraphChangeRequest(
            GraphChangeTarget.DEFINITION_DELTA,
            GraphChange(anchor_upserts=(Anchor("x", "person", "Prospective"),)),
        )
        assert system.apply_graph_change(request, provenance=OWNER).accepted
        assert system.apply_graph_change(
            GraphChange(associated_data_upserts=(AssociatedDataObject("x", "note", ("h",), {}),)),
            provenance=OWNER,
        ).accepted

        rejected = system.apply_graph_change(request, provenance=OWNER)

        assert not rejected.accepted
        assert materialize_state(system).graph.associated_data_object("x") is not None
    finally:
        system.close()


def test_assessment_incident_seek_ignores_historical_link_versions(tmp_path: Path) -> None:
    project = AnchorTypeDefinition("project", "A project.")

    def measured_steps(version_count: int) -> int:
        system = RTGSystem.open(tmp_path / f"current-link-index-{version_count}.sqlite3")
        try:
            assert system.initialize_fresh(
                GraphDefinitionSet(
                    anchor_types=(PERSON, project),
                    link_types=(
                        LinkTypeDefinition(
                            "works",
                            EndpointConstraint(("person",), ("project",), "Endpoints."),
                            "Work.",
                        ),
                    ),
                ),
                provenance=OWNER,
                initialization_summary="fresh",
            ).accepted
            assert system.apply_graph_change(
                GraphChange(
                    anchor_upserts=(
                        Anchor("p", "person", "Person"),
                        Anchor("j", "project", "Project"),
                    ),
                    link_upserts=(Link("l", "works", "p", "j"),),
                ),
                provenance=OWNER,
            ).accepted
            for index in range(version_count):
                assert system.apply_graph_change(
                    GraphChange(
                        link_upserts=(
                            Link(
                                "l",
                                "works",
                                "p",
                                "j",
                                system_metadata=SystemMetadata({"version": Decimal(index)}),
                            ),
                        )
                    ),
                    provenance=OWNER,
                ).accepted
            assert system.apply_graph_change(
                GraphChangeRequest(
                    GraphChangeTarget.DEFINITION_DELTA,
                    GraphChange(anchor_upserts=(Anchor("p", "person", "Updated"),)),
                ),
                provenance=OWNER,
            ).accepted
            steps = 0

            def progress() -> int:
                nonlocal steps
                steps += 100
                return 0

            system.store._connection.set_progress_handler(progress, 100)  # noqa: SLF001
            report = _assess_delta(system)
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001

            assert report.conforms
            return steps
        finally:
            system.close()

    baseline_steps = measured_steps(0)
    historical_steps = measured_steps(500)

    assert historical_steps <= baseline_steps + 200
