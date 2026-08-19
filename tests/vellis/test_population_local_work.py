"""Resource evidence for SQLite-native population-local ordinary work."""

from __future__ import annotations

import ast
import hashlib
import io
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import vellis.streaming as streaming
from vellis.canonical import Provenance
from vellis.changes import GraphChange, GraphChangeRequest, GraphChangeTarget
from vellis.definitions import (
    AnchorTypeDefinition,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
)
from vellis.discovery import DefinitionInspectionRequest
from vellis.governance import (
    ActivateDefinitionDeltaRequest,
    DefinitionChange,
    LinkMultiplicitySelection,
)
from vellis.graph import Anchor
from vellis.history import RevisionSelection
from vellis.normalized import normalized_state_identity, recomputed_graph_summary
from vellis.outcomes import (
    OperationStatus,
    ValidationRequest,
    ValidationRequestKind,
    ValidationScope,
)
from vellis.store import StoreError
from vellis.streaming import export_ndjson, export_tail_ndjson, import_ndjson
from vellis.system import RTGSystem

OWNER = Provenance("owner")
DEFINITIONS = GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),))


def _system(path: Path, population: int) -> RTGSystem:
    system = RTGSystem.open(path)
    assert system.initialize_fresh(
        DEFINITIONS, provenance=OWNER, initialization_summary="fresh"
    ).accepted
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=tuple(
                Anchor(f"a-{index}", "person", f"Person {index}") for index in range(population)
            )
        ),
        provenance=OWNER,
    ).accepted
    return system


def _steps(system: RTGSystem, operation: Callable[[], object]) -> int:
    count = 0

    def progress() -> int:
        nonlocal count
        count += 1
        return 0

    system.store._connection.set_progress_handler(progress, 1)  # noqa: SLF001
    try:
        result = operation()
    finally:
        system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001
    assert getattr(result, "accepted", False), result
    return count


def _ordinary_write_steps(path: Path, population: int) -> tuple[int, ...]:
    system = _system(path, population)
    try:
        measured = [
            _steps(
                system,
                lambda: system.apply_graph_change(
                    GraphChange(anchor_upserts=(Anchor("a-0", "person", "Active"),)),
                    provenance=OWNER,
                ),
            ),
            _steps(
                system,
                lambda: system.apply_graph_change(
                    GraphChangeRequest(
                        GraphChangeTarget.DEFINITION_DELTA,
                        GraphChange(anchor_upserts=(Anchor("a-0", "person", "Prospective"),)),
                    ),
                    provenance=OWNER,
                ),
            ),
            _steps(system, lambda: system.discard_definition_delta(provenance=OWNER)),
            _steps(
                system,
                lambda: system.set_definition_delta(
                    DefinitionChange(
                        anchor_type_upserts=(AnchorTypeDefinition("person", "A described person."),)
                    ),
                    provenance=OWNER,
                ),
            ),
        ]
        assessment = system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.DEFINITION_DELTA,
                maximum_findings=10,
            )
        )
        assert assessment.accepted and assessment.conforms
        assert assessment.assessment_id is not None
        assessment_id = assessment.assessment_id
        measured.append(
            _steps(
                system,
                lambda: system.activate_definition_delta(
                    ActivateDefinitionDeltaRequest(assessment_id),
                    provenance=OWNER,
                ),
            )
        )
        return tuple(measured)
    finally:
        system.close()


def test_ordinary_writes_are_independent_of_unrelated_graph_population(tmp_path: Path) -> None:
    small = _ordinary_write_steps(tmp_path / "small.sqlite3", 10)
    large = _ordinary_write_steps(tmp_path / "large.sqlite3", 4_000)

    assert large == small


@pytest.mark.parametrize("population", (10, 4_000))
def test_focused_definition_frontier_is_independent_of_unrelated_definitions(
    tmp_path: Path, population: int
) -> None:
    definitions = GraphDefinitionSet(
        anchor_types=tuple(
            AnchorTypeDefinition(f"type-{index}", f"Type {index}.") for index in range(population)
        )
    )
    system = RTGSystem.open(tmp_path / f"definitions-{population}.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=OWNER, initialization_summary="large vocabulary"
        ).accepted
        steps = _steps(
            system,
            lambda: system.inspect_definitions(DefinitionInspectionRequest(("type-0",))),
        )
        assert steps < 500
    finally:
        system.close()


def test_connected_definition_frontier_processes_each_edge_once(tmp_path: Path) -> None:
    def measured(length: int, name: str) -> int:
        definitions = GraphDefinitionSet(
            anchor_types=tuple(
                AnchorTypeDefinition(f"type-{index}", f"Type {index}.")
                for index in range(length + 1)
            ),
            link_types=tuple(
                LinkTypeDefinition(
                    f"link-{index}",
                    EndpointConstraint(
                        (f"type-{index}",),
                        (f"type-{index + 1}",),
                        "The next type.",
                    ),
                    "A chain edge.",
                )
                for index in range(length)
            ),
        )
        system = RTGSystem.open(tmp_path / name)
        try:
            assert system.initialize_fresh(
                definitions, provenance=OWNER, initialization_summary="connected vocabulary"
            ).accepted
            return _steps(
                system,
                lambda: system.inspect_definitions(DefinitionInspectionRequest(("type-0",))),
            )
        finally:
            system.close()

    small = measured(50, "chain-small.sqlite3")
    large = measured(400, "chain-large.sqlite3")

    assert large < small * 9


def test_ordinary_rule_lookup_ignores_four_thousand_unrelated_rules(
    tmp_path: Path,
) -> None:
    definitions = GraphDefinitionSet(
        anchor_types=(
            AnchorTypeDefinition("focus", "The touched type."),
            AnchorTypeDefinition("other", "An unrelated type."),
        ),
        link_types=tuple(
            LinkTypeDefinition(
                f"unrelated-{index}",
                EndpointConstraint(("other",), ("other",), "Unrelated endpoints."),
                "An unrelated link.",
            )
            for index in range(4_000)
        ),
        relationship_constraints=tuple(
            LinkMultiplicityConstraint(
                f"unrelated-{index}",
                LinkEnd.SOURCE,
                ("other",),
                ("other",),
                0,
                None,
                "An unrelated bound.",
            )
            for index in range(4_000)
        ),
    )
    system = RTGSystem.open(tmp_path / "unrelated-rules.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=OWNER, initialization_summary="large rule population"
        ).accepted
        steps = _steps(
            system,
            lambda: system.apply_graph_change(
                GraphChange(anchor_upserts=(Anchor("focus", "focus", "Focus"),)),
                provenance=OWNER,
            ),
        )

        assert steps < 2_000
    finally:
        system.close()


def test_repeated_activation_cost_depends_on_the_new_edit_not_prior_overrides(
    tmp_path: Path,
) -> None:
    def measured(prior_edits: int, name: str) -> int:
        definitions = GraphDefinitionSet(
            anchor_types=tuple(
                AnchorTypeDefinition(f"type-{index}", "Original.")
                for index in range(prior_edits + 1)
            )
        )
        system = RTGSystem.open(tmp_path / name)
        try:
            assert system.initialize_fresh(
                definitions, provenance=OWNER, initialization_summary="definition population"
            ).accepted
            assert system.set_definition_delta(
                DefinitionChange(
                    anchor_type_upserts=tuple(
                        AnchorTypeDefinition(f"type-{index}", "First edit.")
                        for index in range(prior_edits)
                    )
                ),
                provenance=OWNER,
            ).accepted
            first = system.check(
                ValidationRequest(
                    ValidationRequestKind.ASSESS,
                    ValidationScope.DEFINITION_DELTA,
                    maximum_findings=10,
                )
            )
            assert first.accepted and first.assessment_id is not None
            assert system.activate_definition_delta(
                ActivateDefinitionDeltaRequest(first.assessment_id), provenance=OWNER
            ).accepted
            assert system.set_definition_delta(
                DefinitionChange(
                    anchor_type_upserts=(
                        AnchorTypeDefinition(f"type-{prior_edits}", "Second edit."),
                    )
                ),
                provenance=OWNER,
            ).accepted
            second = system.check(
                ValidationRequest(
                    ValidationRequestKind.ASSESS,
                    ValidationScope.DEFINITION_DELTA,
                    maximum_findings=10,
                )
            )
            assert second.accepted and second.assessment_id is not None
            second_assessment_id = second.assessment_id
            return _steps(
                system,
                lambda: system.activate_definition_delta(
                    ActivateDefinitionDeltaRequest(second_assessment_id), provenance=OWNER
                ),
            )
        finally:
            system.close()

    assert measured(1_000, "many-overrides.sqlite3") == measured(10, "few-overrides.sqlite3")


def test_historical_frontier_uses_definition_membership_at_that_revision(
    tmp_path: Path,
) -> None:
    system = RTGSystem.open(tmp_path / "historical-membership.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(AnchorTypeDefinition("person", "A person."),),
                link_types=(
                    LinkTypeDefinition(
                        "friend",
                        EndpointConstraint(("person",), ("person",), "People."),
                        "A friendship.",
                    ),
                ),
            ),
            provenance=OWNER,
            initialization_summary="friend vocabulary",
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(type_removals=("friend",)), provenance=OWNER
        ).accepted
        assessment = system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.DEFINITION_DELTA,
                maximum_findings=10,
            )
        )
        assert assessment.accepted and assessment.assessment_id is not None
        assert system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
        ).accepted

        historical = system.inspect_definitions(
            replace(
                DefinitionInspectionRequest(("person",)),
                state=RevisionSelection(kind="revision", revision=0),
            ),
        )
        assert historical.accepted
        assert {value.type_key for value in historical.anchor_details[0].link_types} == {"friend"}
    finally:
        system.close()


def test_deleted_rule_overrides_do_not_expand_focused_mutation_work(tmp_path: Path) -> None:
    count = 1_000
    rules = tuple(
        LinkMultiplicityConstraint(
            f"unrelated-{index}",
            LinkEnd.SOURCE,
            ("other",),
            ("other",),
            0,
            None,
            "Unrelated.",
        )
        for index in range(count)
    )
    system = RTGSystem.open(tmp_path / "deleted-rules.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(
                    AnchorTypeDefinition("focus", "Focus."),
                    AnchorTypeDefinition("other", "Other."),
                ),
                link_types=tuple(
                    LinkTypeDefinition(
                        f"unrelated-{index}",
                        EndpointConstraint(("other",), ("other",), "Other."),
                        "Unrelated.",
                    )
                    for index in range(count)
                ),
                relationship_constraints=rules,
            ),
            provenance=OWNER,
            initialization_summary="rules",
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(
                link_multiplicity_removals=tuple(
                    LinkMultiplicitySelection(
                        rule.link_type_key,
                        rule.constrained_end,
                        rule.constrained_endpoint_type_keys,
                        rule.opposite_endpoint_type_keys,
                    )
                    for rule in rules
                )
            ),
            provenance=OWNER,
        ).accepted
        assessment = system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.DEFINITION_DELTA,
                maximum_findings=10,
            )
        )
        assert assessment.accepted and assessment.assessment_id is not None
        assert system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
        ).accepted
        steps = _steps(
            system,
            lambda: system.apply_graph_change(
                GraphChange(anchor_upserts=(Anchor("focus", "focus", "Focus"),)),
                provenance=OWNER,
            ),
        )
        assert steps < 2_000
    finally:
        system.close()


def test_tail_from_a_structurally_shared_active_set_preserves_later_proposal(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    system = RTGSystem.open(source_path)
    snapshot = io.StringIO()
    tail = io.StringIO()
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(
                    AnchorTypeDefinition("first", "Original first."),
                    AnchorTypeDefinition("second", "Original second."),
                )
            ),
            provenance=OWNER,
            initialization_summary="two definitions",
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(
                anchor_type_upserts=(AnchorTypeDefinition("first", "Changed first."),)
            ),
            provenance=OWNER,
        ).accepted
        assessment = system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.DEFINITION_DELTA,
                maximum_findings=10,
            )
        )
        assert assessment.accepted and assessment.assessment_id is not None
        assert system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=OWNER
        ).accepted
        captured = export_ndjson(source_path, snapshot)
        assert system.set_definition_delta(
            DefinitionChange(
                anchor_type_upserts=(AnchorTypeDefinition("second", "Changed second."),)
            ),
            provenance=OWNER,
        ).accepted
        expected = system.definition_delta().proposed_definition_identity
    finally:
        system.close()
    export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
    )
    snapshot.seek(0)
    tail.seek(0)
    import_ndjson(snapshot, target_path, tail=tail)
    restored = RTGSystem.open(target_path)
    try:
        assert restored.definition_delta().proposed_definition_identity == expected
        assert restored.store.verify_projection_from_ledger() == ()
    finally:
        restored.close()


@pytest.mark.parametrize("population", (10, 4_000))
def test_adjacent_restore_depends_on_changed_tail_uuids_not_population(
    tmp_path: Path, population: int
) -> None:
    system = RTGSystem.open(tmp_path / f"restore-{population}.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=tuple(
                    AnchorTypeDefinition(f"type-{index}", "A type.") for index in range(population)
                )
            ),
            provenance=OWNER,
            initialization_summary="definition population",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-0", "type-0", "Original"),)),
            provenance=OWNER,
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-0", "type-0", "Changed"),)),
            provenance=OWNER,
        ).accepted
        steps = _steps(
            system,
            lambda: system.restore_historical_state(
                RevisionSelection(kind="revision", revision=1), provenance=OWNER
            ),
        )
        assert steps < 2_000
    finally:
        system.close()


def test_state_identity_reads_only_maintained_summaries(tmp_path: Path) -> None:
    system = _system(tmp_path / "identity.sqlite3", 4_000)
    statements: list[str] = []
    try:
        system.store._connection.set_trace_callback(statements.append)  # noqa: SLF001
        normalized_state_identity(system.store._connection)  # noqa: SLF001
    finally:
        system.store._connection.set_trace_callback(None)  # noqa: SLF001
        system.close()

    assert all("current_graph_object" not in statement for statement in statements)
    assert all("object_value" not in statement for statement in statements)


def test_summary_drift_is_rejected_at_explicit_integrity_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "drift.sqlite3"
    system = _system(path, 25)
    try:
        system.store._connection.execute(  # noqa: SLF001
            "UPDATE state_head SET graph_accumulator = ? WHERE id = 0", ("f" * 64,)
        )
        findings = system.store.verify_projection_from_ledger()
        assert any("graph summary" in finding.summary for finding in findings)
        with pytest.raises(StoreError, match="graph summary"):
            export_ndjson(path, io.StringIO())

        count, accumulator = recomputed_graph_summary(system.store._connection)  # noqa: SLF001
        system.store._connection.execute(  # noqa: SLF001
            "UPDATE state_head SET graph_entry_count = ?, graph_accumulator = ? WHERE id = 0",
            (count, accumulator),
        )
        assert system.store.verify_projection_from_ledger() == ()
    finally:
        system.close()


@pytest.mark.parametrize(
    "corruption, expected",
    (
        (
            "UPDATE proposal_overlay_state SET accumulator ="
            " 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
            "proposal overlay summary",
        ),
        (
            "UPDATE proposal_overlay_count SET entry_count = entry_count + 1"
            " WHERE object_kind = 'anchor' AND operation = 'upsert'",
            "proposal overlay counts",
        ),
        (
            "UPDATE proposal_definition_state SET effective_accumulator ="
            " 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
            "proposal effective definition summary",
        ),
    ),
)
def test_every_proposal_summary_drift_is_rejected(
    tmp_path: Path, corruption: str, expected: str
) -> None:
    path = tmp_path / (expected.replace(" ", "-") + ".sqlite3")
    system = _system(path, 10)
    try:
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("a-0", "person", "Proposed"),)),
            ),
            provenance=OWNER,
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("person", "Changed."),)),
            provenance=OWNER,
        ).accepted
        system.store._connection.execute(corruption)  # noqa: SLF001

        findings = system.store.verify_projection_from_ledger()
        assert any(expected in finding.summary for finding in findings)
        with pytest.raises(StoreError, match=expected):
            export_ndjson(path, io.StringIO())
    finally:
        system.close()


@pytest.mark.parametrize("population", (10, 4_000))
def test_one_tail_record_adds_bounded_vm_work_over_the_snapshot_import(
    tmp_path: Path, population: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / f"tail-source-{population}.sqlite3"
    system = _system(source_path, population)
    snapshot_path = tmp_path / f"snapshot-{population}.ndjson"
    tail_path = tmp_path / f"tail-{population}.ndjson"
    try:
        with snapshot_path.open("w", encoding="utf-8") as output:
            captured = export_ndjson(source_path, output)
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("tail", "person", "Tail"),)),
            provenance=OWNER,
        ).accepted
        with tail_path.open("w", encoding="utf-8") as output:
            export_tail_ndjson(
                source_path,
                output,
                after_revision=captured.revision,
                after_record_identity=captured.record_identity,
            )
    finally:
        system.close()

    real_connect = sqlite3.connect

    def measured(destination: Path, *, with_tail: bool) -> int:
        steps = 0

        def counting_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
            nonlocal steps
            connection = real_connect(*args, **kwargs)  # type: ignore[arg-type]

            def progress() -> int:
                nonlocal steps
                steps += 100
                return 0

            connection.set_progress_handler(progress, 100)
            return connection

        monkeypatch.setattr(streaming.sqlite3, "connect", counting_connect)
        try:
            with snapshot_path.open(encoding="utf-8") as snapshot:
                if with_tail:
                    with tail_path.open(encoding="utf-8") as tail:
                        import_ndjson(snapshot, destination, tail=tail)
                else:
                    import_ndjson(snapshot, destination)
        finally:
            monkeypatch.setattr(streaming.sqlite3, "connect", real_connect)
        return steps

    snapshot_steps = measured(tmp_path / f"snapshot-only-{population}.sqlite3", with_tail=False)
    tail_steps = measured(tmp_path / f"with-tail-{population}.sqlite3", with_tail=True)

    assert abs(tail_steps - snapshot_steps) < 20_000


_SELECTED_CURRENT_GRAPH_READS = Counter(
    {
        (
            "normalized.py",
            "recomputed_graph_summary",
            "b93b2819f096fdd64391513b57c66a4831b35f03f88fb99cd274e459a691ce14",
            1,
        ): 1,
        ("store.py", "", "612fc13a8a811b1f48d3312765e07f1ff9387e08809074c0ee6ed99e234a0f2a", 3): 1,
        (
            "store.py",
            "_evaluate_compiled_query_unlocked",
            "1955bafb8db41dd91b583f4bfdffe6e4472caef5224e4eef96b07ecbbb0fe7cb",
            1,
        ): 1,
        (
            "store.py",
            "_effective_type_keys_unlocked",
            "1955bafb8db41dd91b583f4bfdffe6e4472caef5224e4eef96b07ecbbb0fe7cb",
            1,
        ): 1,
        (
            "store.py",
            "_iter_definition_findings_unlocked",
            "1955bafb8db41dd91b583f4bfdffe6e4472caef5224e4eef96b07ecbbb0fe7cb",
            1,
        ): 1,
        (
            "store.py",
            "_iter_multiplicity_findings_unlocked",
            "1955bafb8db41dd91b583f4bfdffe6e4472caef5224e4eef96b07ecbbb0fe7cb",
            1,
        ): 1,
        (
            "store.py",
            "conformance_context",
            "1955bafb8db41dd91b583f4bfdffe6e4472caef5224e4eef96b07ecbbb0fe7cb",
            1,
        ): 1,
        (
            "store.py",
            "iter_conformance_findings",
            "1955bafb8db41dd91b583f4bfdffe6e4472caef5224e4eef96b07ecbbb0fe7cb",
            1,
        ): 1,
        (
            "store.py",
            "_base_value_for_proposal_unlocked",
            "9bc0788b864d2f68b5b5fb316b398dad9d874c68d3f3efec7ad24e3d811421ee",
            1,
        ): 1,
        (
            "store.py",
            "_initialize_base",
            "1955bafb8db41dd91b583f4bfdffe6e4472caef5224e4eef96b07ecbbb0fe7cb",
            1,
        ): 1,
        (
            "store.py",
            "_active_value_unlocked",
            "9bc0788b864d2f68b5b5fb316b398dad9d874c68d3f3efec7ad24e3d811421ee",
            1,
        ): 1,
        (
            "store.py",
            "_objects_for_uuids_unlocked",
            "969b5d2f5237b8b7062ca85d6dcc40c6ae1b102bedc324137ebbf277a6de7219",
            1,
        ): 1,
        (
            "store.py",
            "_proposal_command_findings_unlocked",
            "fd59d4942eb498e7708c09ed8a4edd8d5b54b5cde403870ed7214d50266b598d",
            1,
        ): 1,
        (
            "store.py",
            "activate_proposal",
            "ef483f98dc1743bd69d029f958349f3cc9649df767e7179f8cc563f0e385232a",
            1,
        ): 1,
        (
            "store.py",
            "verify_projection_from_ledger",
            "98321e2e4df0ed502359fd23a5a97a57e8ae7ac1d90f780e07fe4188517a0c71",
            2,
        ): 1,
        (
            "store.py",
            "restore_revision",
            "b2afeb6120336cb1130335365dfef5319499bac04505c476e40f81f498aa40c9",
            1,
        ): 1,
        (
            "store.py",
            "_referencing_uuids_unlocked",
            "7c1223c1f2a1f102424dacd9802a038416d7df3da1ce7b3317206ac8e43b460e",
            1,
        ): 1,
        (
            "store.py",
            "_incident_relationship_uuids_unlocked",
            "e90e7e86b66e3b3fcff22256b818ee8cc715ce8d1c4ddc2f2852985ae22eaf07",
            1,
        ): 1,
        (
            "store.py",
            "_apply_current_graph_change_unlocked",
            "419bee92849096d4eb0c01edcd9d901aef8a704684f6f1f2ffdbf96331d2a95b",
            1,
        ): 1,
        (
            "streaming.py",
            "_tail_event_error",
            "a3fd5105391b9da18f8a95f8881985b00102f4d25042f8f971c214a448c8aba9",
            1,
        ): 2,
        (
            "streaming.py",
            "_apply_tail_stream",
            "1955bafb8db41dd91b583f4bfdffe6e4472caef5224e4eef96b07ecbbb0fe7cb",
            1,
        ): 1,
        (
            "streaming.py",
            "_apply_tail_stream",
            "b2afeb6120336cb1130335365dfef5319499bac04505c476e40f81f498aa40c9",
            1,
        ): 1,
        (
            "streaming.py",
            "_apply_tail_stream",
            "9bc0788b864d2f68b5b5fb316b398dad9d874c68d3f3efec7ad24e3d811421ee",
            1,
        ): 1,
    }
)


def _static_string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string_value(node.left)
        right = _static_string_value(node.right)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.FormattedValue) and node.format_spec is None:
        value = _static_string_value(node.value)
        if value is None:
            return None
        if node.conversion == ord("r"):
            return repr(value)
        if node.conversion == ord("a"):
            return ascii(value)
        return value
    if isinstance(node, ast.JoinedStr):
        parts = [_static_string_value(part) for part in node.values]
        return "".join(cast(list[str], parts)) if all(part is not None for part in parts) else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
        and len(node.args) == 1
        and isinstance(node.args[0], (ast.List, ast.Tuple))
    ):
        separator = _static_string_value(node.func.value)
        parts = [_static_string_value(part) for part in node.args[0].elts]
        if separator is not None and all(part is not None for part in parts):
            return separator.join(part for part in parts if part is not None)
    return None


def _literal_current_graph_read_violations(
    path_name: str, source: str
) -> tuple[list[str], Counter[tuple[str, str, str, int]]]:
    """Inventory exact reviewed production literals; every changed shape requires review."""
    observed: Counter[tuple[str, str, str, int]] = Counter()
    violations: list[str] = []
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        value = _static_string_value(node)
        if value is None:
            continue
        parent = parents.get(node)
        while parent is not None and not isinstance(
            parent, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if _static_string_value(parent) is not None:
                break
            parent = parents.get(parent)
        if parent is not None and _static_string_value(parent) is not None:
            continue
        owner: ast.AST = node
        while owner in parents and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = parents[owner]
        function = owner.name if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)) else ""
        normalized = " ".join(value.upper().split())
        reference_count = normalized.count("CURRENT_GRAPH_OBJECT")
        if not reference_count:
            continue
        fingerprint = hashlib.sha256(normalized.encode()).hexdigest()
        key = (path_name, function, fingerprint, reference_count)
        observed[key] += 1
        if observed[key] > _SELECTED_CURRENT_GRAPH_READS[key]:
            violations.append(
                f"{path_name}:{getattr(node, 'lineno', 0)}:{function}:unselected-literal"
            )
    return violations, observed


def _current_graph_read_inventory(
    source_root: Path,
) -> tuple[list[str], Counter[tuple[str, str, str, int]]]:
    violations: list[str] = []
    observed: Counter[tuple[str, str, str, int]] = Counter()
    for path in sorted(source_root.rglob("*.py")):
        relative_path = path.relative_to(source_root).as_posix()
        path_violations, path_observed = _literal_current_graph_read_violations(
            relative_path, path.read_text(encoding="utf-8")
        )
        violations.extend(path_violations)
        observed.update(path_observed)
    return violations, observed


@pytest.mark.parametrize(
    "query",
    (
        "SELECT uuid FROM\ncurrent_graph_object",
        "SELECT value.id FROM object_value AS value JOIN current_graph_object AS current ON true",
        "SELECT uuid FROM current_graph_object; SELECT 1 WHERE 1",
        "SELECT 1 WHERE 1 UNION ALL SELECT uuid FROM current_graph_object",
        "SELECT uuid FROM current_graph_object WHERE 1",
        "WITH x AS (SELECT uuid FROM current_graph_object) SELECT uuid FROM x WHERE uuid = ?",
        "SELECT uuid FROM current_graph_object WHERE uuid = ? OR 1",
        "SELECT uuid FROM current_graph_object WHERE object_kind = 'link' OR 1",
        "SELECT uuid FROM current_graph_object WHERE uuid IN "
        "(SELECT uuid FROM current_graph_object)",
        "SELECT c.uuid FROM current_graph_object c JOIN current_graph_object other ON true "
        "WHERE c.uuid = ?",
        "-- ordinary read\nSELECT uuid FROM current_graph_object",
        "INSERT INTO scratch SELECT uuid FROM current_graph_object",
    ),
)
def test_current_graph_scan_guard_rejects_unbounded_literal_shapes(query: str) -> None:
    source = f"def ordinary_read():\n    return {query!r}\n"

    violations, _ = _literal_current_graph_read_violations("ordinary.py", source)

    assert violations == ["ordinary.py:2:ordinary_read:unselected-literal"]


def test_current_graph_scan_guard_rejects_a_concatenated_table_literal() -> None:
    source = "def ordinary_read():\n    return 'SELECT uuid FROM current_' + 'graph_object'\n"

    violations, _ = _literal_current_graph_read_violations("ordinary.py", source)

    assert violations == ["ordinary.py:2:ordinary_read:unselected-literal"]


def test_current_graph_scan_guard_rejects_a_joined_table_literal() -> None:
    source = (
        "def ordinary_read():\n    return ''.join(('SELECT uuid FROM current_', 'graph_object'))\n"
    )

    violations, _ = _literal_current_graph_read_violations("ordinary.py", source)

    assert violations == ["ordinary.py:2:ordinary_read:unselected-literal"]


def test_current_graph_scan_guard_rejects_a_literal_only_f_string() -> None:
    source = "def ordinary_read():\n    return f\"SELECT uuid FROM current_{'graph_object'}\"\n"

    violations, _ = _literal_current_graph_read_violations("ordinary.py", source)

    assert violations == ["ordinary.py:2:ordinary_read:unselected-literal"]


def test_current_graph_scan_guard_discovers_nested_production_modules(tmp_path: Path) -> None:
    nested = tmp_path / "feature" / "ordinary.py"
    nested.parent.mkdir(mode=0o700)
    nested.write_text(
        "def ordinary_read():\n    return 'SELECT uuid FROM current_graph_object'\n",
        encoding="utf-8",
    )

    violations, observed = _current_graph_read_inventory(tmp_path)

    assert observed
    assert violations == ["feature/ordinary.py:2:ordinary_read:unselected-literal"]


def test_current_graph_scan_guard_rejects_changed_selected_state_wide_literals() -> None:
    source = (
        "def recomputed_graph_summary():\n"
        "    first = 'SELECT uuid FROM current_graph_object'\n"
        "    return first, 'SELECT object_value_id FROM current_graph_object'\n"
    )

    violations, selected = _literal_current_graph_read_violations("normalized.py", source)

    assert selected
    assert violations == [
        "normalized.py:2:recomputed_graph_summary:unselected-literal",
        "normalized.py:3:recomputed_graph_summary:unselected-literal",
    ]


def test_every_literal_current_graph_read_is_bounded_or_selected_state_wide() -> None:
    """Guard unexercised SQLite paths while runtime characterization remains primary evidence."""
    source_root = Path(__file__).parents[2] / "vellis"
    violations, observed = _current_graph_read_inventory(source_root)

    assert observed == _SELECTED_CURRENT_GRAPH_READS
    assert violations == []


def test_graph_rows_head_summary_and_record_roll_back_together(tmp_path: Path) -> None:
    system = _system(tmp_path / "rollback.sqlite3", 10)
    try:
        before = system.store._connection.execute(  # noqa: SLF001
            "SELECT revision, graph_entry_count, graph_accumulator FROM state_head WHERE id = 0"
        ).fetchone()
        system.store._connection.execute(  # noqa: SLF001
            "CREATE TEMP TRIGGER fail_summary BEFORE UPDATE OF graph_accumulator ON state_head"
            " BEGIN SELECT RAISE(ABORT, 'injected summary failure'); END"
        )

        result = system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("new", "person", "New"),)),
            provenance=OWNER,
        )

        assert result.status is OperationStatus.FAILED
        assert (
            system.store._connection.execute(  # noqa: SLF001
                "SELECT revision, graph_entry_count, graph_accumulator FROM state_head WHERE id = 0"
            ).fetchone()
            == before
        )
        assert (
            system.store._connection.execute(  # noqa: SLF001
                "SELECT 1 FROM current_graph_object WHERE uuid = 'new'"
            ).fetchone()
            is None
        )
    finally:
        system.close()


def test_full_assessment_decodes_each_encountered_type_neighborhood_once(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path / "assessment.sqlite3", 4_000)
    try:
        system.store.reset_instrumentation()
        report = system.check(
            ValidationRequest(
                ValidationRequestKind.ASSESS,
                ValidationScope.GRAPH_CONFORMANCE,
                maximum_findings=10,
            )
        )

        assert report.accepted and report.conforms
        assert system.store.current_definition_decodes == 3
    finally:
        system.close()
