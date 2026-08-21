"""Discriminating Phase 4 evidence for patches and the sole draft bucket."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import pytest

import vellis.change_operations as change_module
import vellis.draft_activation as activation_module
import vellis.draft_inspection_operations as inspection_module
import vellis.draft_operations as draft_module
import vellis.draft_read_operations as draft_read_module
import vellis.draft_repository as draft_repository_module
import vellis.read_operations as read_module
from vellis.audit import audit_database
from vellis.change_domain import (
    DraftCategory,
    DraftChangeRequest,
    DraftInspectionRequest,
    DraftOperation,
    ValidationRequest,
    ValidationScope,
)
from vellis.change_operations import apply_graph_change
from vellis.discovery_operations import type_inspect, type_summary
from vellis.domain import (
    Anchor,
    AnchorTypeDefinition,
    AnchorUpsert,
    AssociatedData,
    AssociatedDataTypeDefinition,
    AssociatedDataUpsert,
    Cardinality,
    DraftState,
    FindingCode,
    GraphChangeRequest,
    Link,
    LinkTypeDefinition,
    LinkUpsert,
    OperationStatus,
    PropertyDefinition,
    ScalarValue,
    ValueKind,
)
from vellis.draft_inspection_operations import inspect_draft
from vellis.draft_operations import (
    activate_draft,
    change_draft,
    discard_draft,
    validate_state,
)
from vellis.operations import initialize_with_definitions, read_state
from vellis.query_domain import (
    DirectAssociation,
    DisplayNameField,
    GraphQuery,
    IdentityObjectSelection,
    IdentitySelection,
    PatternLink,
    PatternNode,
    PatternNodeKind,
    PatternQueryPayload,
    PatternSelection,
    Predicate,
    PredicateOperator,
    PropertyField,
    PropertySelection,
)
from vellis.read_operations import query_graph

PERSON = "11111111-1111-4111-8111-111111111111"
PERSON_2 = "22222222-2222-4222-8222-222222222222"
GROUP = "33333333-3333-4333-8333-333333333333"
DATA = "44444444-4444-4444-8444-444444444444"
LINK = "55555555-5555-4555-8555-555555555555"
GROUP_2 = "66666666-6666-4666-8666-666666666666"
GROUP_3 = "77777777-7777-4777-8777-777777777777"
LINK_2 = "88888888-8888-4888-8888-888888888888"
LINK_3 = "99999999-9999-4999-8999-999999999999"


def _definitions():
    return (
        AnchorTypeDefinition("test.person", "Person"),
        AnchorTypeDefinition("test.group", "Group"),
        AssociatedDataTypeDefinition(
            "test.details",
            "Details",
            ("test.person", "test.group"),
            (
                PropertyDefinition("note", "Note", ValueKind.TEXT),
                PropertyDefinition("maybe", "Nullable", ValueKind.TEXT, nullable=True),
            ),
            Cardinality(1, 2),
            Cardinality(0, 2),
        ),
        LinkTypeDefinition(
            "test.member",
            "Member",
            ("test.person",),
            ("test.group",),
            Cardinality(0),
            Cardinality(0),
        ),
    )


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "owner" / "vellis.db"
    initialize_with_definitions(path, _definitions(), recorded_at="2026-08-20T00:00:00Z")
    return path


def _seed(path: Path) -> None:
    request = GraphChangeRequest(
        0,
        (
            AnchorUpsert(PERSON, "test.person", "Alice"),
            AnchorUpsert(PERSON_2, "test.person", "Bob"),
            AnchorUpsert(GROUP, "test.group", "Team"),
            AssociatedDataUpsert(
                DATA,
                "test.details",
                (PERSON,),
                set_properties=(("note", ScalarValue.text("original")),),
            ),
            LinkUpsert(LINK, "test.member", PERSON, GROUP),
        ),
    )
    assert apply_graph_change(path, request).resulting_revision == 1


def _objects(path: Path):
    return {value.uuid: value for value in read_state(path).graph}


def _objects_from_state(state):
    return {value.uuid: value for value in state.graph}


def test_field_patches_preserve_unmentioned_content_and_distinguish_null(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    request = GraphChangeRequest(
        1,
        (
            AssociatedDataUpsert(
                DATA,
                add_anchor_uuids=(PERSON_2,),
                set_properties=(("maybe", None),),
            ),
            LinkUpsert(LINK, target_uuid=GROUP),
        ),
    )
    assert apply_graph_change(path, request).resulting_revision == 2
    data = _objects(path)[DATA]
    assert isinstance(data, AssociatedData)
    assert data.anchor_uuids == (PERSON, PERSON_2)
    assert dict(data.properties) == {
        "maybe": None,
        "note": ScalarValue.text("original"),
    }

    remove = GraphChangeRequest(
        2,
        (AssociatedDataUpsert(DATA, remove_properties=("maybe", "absent")),),
    )
    assert apply_graph_change(path, remove).resulting_revision == 3
    data = _objects(path)[DATA]
    assert isinstance(data, AssociatedData)
    assert dict(data.properties) == {"note": ScalarValue.text("original")}


def test_stale_and_conflicting_requests_have_no_state_effect(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    before = read_state(path)
    stale = apply_graph_change(path, GraphChangeRequest(0))
    assert stale.status is OperationStatus.REJECTED
    assert stale.findings[0].code is FindingCode.STALE_REVISION
    conflict = apply_graph_change(
        path,
        GraphChangeRequest(
            1,
            (
                AssociatedDataUpsert(
                    DATA,
                    add_anchor_uuids=(PERSON_2,),
                    remove_anchor_uuids=(PERSON_2,),
                ),
            ),
        ),
    )
    assert conflict.status is OperationStatus.REJECTED
    assert read_state(path) == before


def test_removal_never_cascades_and_names_surviving_dependents(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    rejected = apply_graph_change(path, GraphChangeRequest(1, remove_uuids=(PERSON,)))
    assert rejected.status is OperationStatus.REJECTED
    named = {uuid for finding in rejected.findings for uuid in finding.uuids}
    assert {PERSON, DATA, LINK} <= named
    assert set(_objects(path)) == {PERSON, PERSON_2, GROUP, DATA, LINK}

    accepted = apply_graph_change(
        path,
        GraphChangeRequest(
            1,
            (
                AssociatedDataUpsert(
                    DATA,
                    remove_anchor_uuids=(PERSON,),
                    add_anchor_uuids=(PERSON_2,),
                ),
            ),
            (PERSON, LINK),
        ),
    )
    assert accepted.resulting_revision == 2
    assert set(_objects(path)) == {PERSON_2, GROUP, DATA}


def test_resolved_removal_validates_complete_local_cardinality_peers(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    populated = apply_graph_change(
        path,
        GraphChangeRequest(
            1,
            (
                AnchorUpsert(GROUP_2, "test.group", "Alternate"),
                AnchorUpsert(GROUP_3, "test.group", "Intact"),
                LinkUpsert(LINK_2, "test.member", PERSON_2, GROUP),
                LinkUpsert(LINK_3, "test.member", PERSON, GROUP_3),
            ),
        ),
    )
    assert populated.resulting_revision == 2

    resolved = apply_graph_change(
        path,
        GraphChangeRequest(
            2,
            (LinkUpsert(LINK_2, target_uuid=GROUP_2),),
            (GROUP, LINK),
        ),
    )

    assert resolved.status is OperationStatus.ACCEPTED
    assert resolved.resulting_revision == 3
    objects = _objects(path)
    assert GROUP not in objects
    assert LINK not in objects
    repointed = objects[LINK_2]
    intact = objects[LINK_3]
    assert isinstance(repointed, Link)
    assert repointed.target_uuid == GROUP_2
    assert isinstance(intact, Link)
    assert intact.target_uuid == GROUP_3


def test_batch_permutations_produce_the_same_final_state(tmp_path: Path) -> None:
    paths = (_database(tmp_path / "first"), _database(tmp_path / "second"))
    for path in paths:
        _seed(path)
    upserts = (
        AnchorUpsert(PERSON_2, display_name="Robert"),
        AssociatedDataUpsert(DATA, add_anchor_uuids=(PERSON_2,), remove_anchor_uuids=(PERSON,)),
        LinkUpsert(LINK, source_uuid=PERSON_2),
    )
    first = apply_graph_change(paths[0], GraphChangeRequest(1, upserts))
    second = apply_graph_change(paths[1], GraphChangeRequest(1, tuple(reversed(upserts))))
    assert first == second
    assert read_state(paths[0]) == read_state(paths[1])


def test_active_change_does_not_load_the_complete_graph(tmp_path: Path, monkeypatch) -> None:
    path = _database(tmp_path)
    _seed(path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("ordinary active change loaded the complete graph")

    monkeypatch.setattr("vellis.graph_repository.load_graph", forbidden)
    result = apply_graph_change(
        path, GraphChangeRequest(1, (AnchorUpsert(PERSON, display_name="Alicia"),))
    )
    assert result.resulting_revision == 2


def test_active_validation_does_not_load_unrelated_same_type_population(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    _seed(path)
    unrelated = tuple(f"{index:08x}-aaaa-4aaa-8aaa-{index:012x}" for index in range(1, 41))
    created = apply_graph_change(
        path,
        GraphChangeRequest(
            1,
            tuple(
                AnchorUpsert(uuid, "test.person", f"Unrelated {index}")
                for index, uuid in enumerate(unrelated)
            ),
        ),
    )
    assert created.resulting_revision == 2
    original_load = change_module.load_graph_objects
    loaded: list[tuple[str, ...]] = []

    def recording_load(connection, state, uuids):
        loaded.append(tuple(uuids))
        return original_load(connection, state, uuids)

    monkeypatch.setattr(change_module, "load_graph_objects", recording_load)
    changed = apply_graph_change(
        path, GraphChangeRequest(2, (AnchorUpsert(PERSON, display_name="Alicia"),))
    )
    assert changed.resulting_revision == 3
    assert all(not set(values).intersection(unrelated) for values in loaded)
    assert set().union(*(set(values) for values in loaded)) == {PERSON}


def test_concurrent_changes_use_distinct_connections_and_revision_serialization(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    original_connect = change_module.connect_database
    barrier = Barrier(2)
    lock = Lock()
    connection_ids: list[int] = []

    def synchronized_connect(database_path):
        connection = original_connect(database_path)
        with lock:
            connection_ids.append(id(connection))
        barrier.wait()
        return connection

    monkeypatch.setattr(change_module, "connect_database", synchronized_connect)
    requests = (
        GraphChangeRequest(
            0,
            (AnchorUpsert("99999999-9999-4999-8999-999999999999", "test.person", "One"),),
        ),
        GraphChangeRequest(
            0,
            (AnchorUpsert("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "test.person", "Two"),),
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda request: apply_graph_change(path, request), requests))

    assert len(set(connection_ids)) == 2
    assert sorted(result.status.value for result in results) == ["accepted", "rejected"]
    rejected = next(result for result in results if result.status is OperationStatus.REJECTED)
    assert rejected.findings[0].code is FindingCode.STALE_REVISION


def test_active_noop_records_activity_without_revision(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    result = apply_graph_change(
        path,
        GraphChangeRequest(
            1,
            (AssociatedDataUpsert(DATA, add_anchor_uuids=(PERSON,)),),
            ("66666666-6666-4666-8666-666666666666",),
        ),
    )
    assert result.status is OperationStatus.ACCEPTED
    assert result.resulting_revision is None
    assert read_state(path).evaluated_revision == 1


@pytest.mark.parametrize("variant", ("rejected", "noop", "effective"))
def test_failure_before_serialization_rolls_back_every_active_change_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    before = _persistent_snapshot(path)

    def fail(_value):
        raise RuntimeError("serialization failed")

    monkeypatch.setattr(change_module, "serialize_wire", fail)
    with pytest.raises(RuntimeError, match="serialization failed"):
        if variant == "rejected":
            apply_graph_change(path, GraphChangeRequest(0))
        elif variant == "noop":
            apply_graph_change(path, GraphChangeRequest(1))
        else:
            apply_graph_change(
                path, GraphChangeRequest(1, (AnchorUpsert(PERSON, display_name="Changed"),))
            )
    assert _persistent_snapshot(path) == before
    assert audit_database(path).clean


def _persistent_snapshot(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return "\n".join(connection.iterdump())


@pytest.mark.parametrize("variant", ("missing", "invalid", "redundant", "effective"))
def test_shared_public_projection_failure_rolls_back_every_activation_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    if variant == "invalid":
        change_draft(
            path,
            DraftChangeRequest(
                object_upserts=(
                    AnchorUpsert("99999999-9999-4999-8999-999999999999", display_name="No type"),
                )
            ),
        )
    elif variant == "redundant":
        change_draft(
            path,
            DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Alice"),)),
        )
    elif variant == "effective":
        change_draft(
            path,
            DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Changed"),)),
        )
    before = _persistent_snapshot(path)

    def fail(_value):
        raise RuntimeError("public projection failed")

    monkeypatch.setattr("vellis.wire.public_result", fail)
    with pytest.raises(RuntimeError, match="public projection failed"):
        activate_draft(path)
    assert _persistent_snapshot(path) == before


@pytest.mark.parametrize("capability", ("change", "inspect", "validate", "activate", "discard"))
def test_shared_public_projection_failure_rolls_back_every_draft_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capability: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    if capability != "change":
        change_draft(
            path,
            DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),)),
        )
    before = _persistent_snapshot(path)

    def fail(_value):
        raise RuntimeError("public projection failed")

    monkeypatch.setattr("vellis.wire.public_result", fail)
    with pytest.raises(RuntimeError, match="public projection failed"):
        if capability == "change":
            change_draft(
                path,
                DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),)),
            )
        elif capability == "inspect":
            inspect_draft(path, DraftInspectionRequest(limit=1))
        elif capability == "validate":
            validate_state(path, ValidationRequest(ValidationScope.DRAFT, 1))
        elif capability == "activate":
            activate_draft(path)
        else:
            discard_draft(path)
    assert _persistent_snapshot(path) == before


@pytest.mark.parametrize("capability", ("inspect", "validate"))
def test_shared_public_projection_failure_rolls_back_continuation_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capability: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AnchorUpsert("99999999-9999-4999-8999-999999999991", display_name="One"),
                AnchorUpsert("99999999-9999-4999-8999-999999999992", display_name="Two"),
            )
        ),
    )
    if capability == "inspect":
        first = inspect_draft(path, DraftInspectionRequest(limit=1))
    else:
        first = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 1))
    assert first.payload is not None and first.payload.cursor is not None
    before = _persistent_snapshot(path)

    def fail(_value):
        raise RuntimeError("public projection failed")

    monkeypatch.setattr("vellis.wire.public_result", fail)
    with pytest.raises(RuntimeError, match="public projection failed"):
        if capability == "inspect":
            inspect_draft(path, DraftInspectionRequest(cursor=first.payload.cursor))
        else:
            validate_state(
                path,
                ValidationRequest(ValidationScope.DRAFT, cursor=first.payload.cursor),
            )
    assert _persistent_snapshot(path) == before


@pytest.mark.parametrize("capability", ("change", "inspect", "validate", "activate", "discard"))
def test_draft_activity_failure_rolls_back_capability_effect(
    tmp_path: Path, monkeypatch, capability: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    if capability != "change":
        change_draft(
            path,
            DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),)),
        )
    before = read_state(path)

    def fail(*_args, **_kwargs):
        raise RuntimeError("activity failed")

    target = inspection_module if capability == "inspect" else draft_module
    monkeypatch.setattr(target, "append_activity", fail)
    with pytest.raises(RuntimeError, match="activity failed"):
        if capability == "change":
            change_draft(
                path,
                DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),)),
            )
        elif capability == "inspect":
            inspect_draft(path, DraftInspectionRequest(limit=1))
        elif capability == "validate":
            validate_state(path, ValidationRequest(ValidationScope.DRAFT, 1))
        elif capability == "activate":
            activate_draft(path)
        else:
            discard_draft(path)
    assert read_state(path) == before
    if capability == "change":
        assert type_summary(path, DraftState()).status is OperationStatus.REJECTED
    else:
        assert type_summary(path, DraftState()).status is OperationStatus.ACCEPTED


def test_post_commit_activation_response_loss_does_not_undo_commit(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Published"),))
    )
    original_connect = draft_module.connect_database

    class CommitThenLoseResponse:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def commit(self):
            self.connection.commit()
            raise RuntimeError("response lost after commit")

    monkeypatch.setattr(
        draft_module,
        "connect_database",
        lambda database_path: CommitThenLoseResponse(original_connect(database_path)),
    )
    with pytest.raises(RuntimeError, match="response lost after commit"):
        activate_draft(path)
    live = read_state(path)
    assert live.evaluated_revision == 2
    published = _objects(path)[PERSON]
    assert isinstance(published, Anchor) and published.display_name == "Published"
    assert type_summary(path, DraftState()).status is OperationStatus.REJECTED


def test_draft_fields_win_while_unstaged_live_fields_follow_live(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    staged = change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON_2, display_name="Draft"),))
    )
    assert staged.payload is not None and staged.payload.raw_entry_count == 1
    live = apply_graph_change(
        path,
        GraphChangeRequest(
            1, (AnchorUpsert(PERSON_2, type_key="test.group", display_name="Live"),)
        ),
    )
    assert live.resulting_revision == 2
    result = query_graph(
        path,
        GraphQuery(IdentitySelection((IdentityObjectSelection(PERSON_2),)), DraftState()),
    )
    value = result.payload.objects[0]  # type: ignore[union-attr]
    assert value.display_name == "Draft"
    assert value.type_key == "test.group"
    assert value.system is not None and value.system.last_changed_revision == 2


def test_partial_absent_draft_patch_and_untyped_null_wait_for_live_base(tmp_path: Path) -> None:
    path = _database(tmp_path)
    partial = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    staged = change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(AssociatedDataUpsert(partial, set_properties=(("maybe", None),)),)
        ),
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    dirty = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 100))
    assert dirty.payload is not None and not dirty.payload.clean
    assert partial in {uuid for finding in dirty.payload.findings for uuid in finding.uuids}

    created = apply_graph_change(
        path,
        GraphChangeRequest(
            0,
            (
                AnchorUpsert(PERSON, "test.person", "Live base"),
                AssociatedDataUpsert(partial, "test.details", (PERSON,)),
            ),
        ),
    )
    assert created.resulting_revision == 1
    selected = query_graph(
        path,
        GraphQuery(
            IdentitySelection((IdentityObjectSelection(partial, PropertySelection(("maybe",))),)),
            DraftState(),
        ),
    )
    value = selected.payload.objects[0]  # type: ignore[union-attr]
    assert value.properties == (("maybe", None),)
    assert value.system is not None and value.system.created_revision == 1
    effective = _objects_from_state(read_state(path, DraftState()))[partial]
    assert isinstance(effective, AssociatedData)
    assert dict(effective.properties) == {"maybe": None}
    inspected = inspect_draft(path, DraftInspectionRequest(limit=10)).payload.entries[0]  # type: ignore[union-attr]
    assert isinstance(inspected.proposed, AssociatedData)
    assert dict(inspected.proposed.properties) == {"maybe": None}
    clean = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 100))
    assert clean.payload is not None and clean.payload.clean
    assert activate_draft(path).outcome.resulting_revision == 2
    published = _objects(path)[partial]
    assert isinstance(published, AssociatedData)
    assert dict(published.properties) == {"maybe": None}


def test_partial_staged_patch_rejects_incompatible_live_kind(tmp_path: Path) -> None:
    path = _database(tmp_path)
    partial = "abababab-abab-4bab-8bab-abababababab"
    change_draft(
        path,
        DraftChangeRequest(object_upserts=(AnchorUpsert(partial, display_name="Draft"),)),
    )
    created = apply_graph_change(
        path,
        GraphChangeRequest(
            0,
            (
                AnchorUpsert(PERSON, "test.person", "Person"),
                AnchorUpsert(GROUP, "test.group", "Group"),
                LinkUpsert(partial, "test.member", PERSON, GROUP),
            ),
        ),
    )
    assert created.resulting_revision == 1
    report = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 100))
    assert report.payload is not None and not report.payload.clean
    assert activate_draft(path).outcome.status is OperationStatus.REJECTED


def test_unmaterializable_inspection_effect_matches_effective_count(tmp_path: Path) -> None:
    path = _database(tmp_path)
    partial = "acacacac-acac-4cac-8cac-acacacacacac"
    result = change_draft(
        path,
        DraftChangeRequest(object_upserts=(AnchorUpsert(partial, display_name="Partial"),)),
    )
    assert result.payload is not None and result.payload.effective_change_count == 0
    entry = inspect_draft(path, DraftInspectionRequest(limit=10)).payload.entries[0]  # type: ignore[union-attr]
    assert entry.proposed is None
    assert not entry.has_effect


def test_absent_data_additions_do_not_substitute_for_complete_anchor_base(tmp_path: Path) -> None:
    path = _database(tmp_path)
    partial = "adadadad-adad-4dad-8dad-adadadadadad"
    apply_graph_change(
        path, GraphChangeRequest(0, (AnchorUpsert(PERSON, "test.person", "Person"),))
    )
    staged = change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AssociatedDataUpsert(
                    partial,
                    "test.details",
                    add_anchor_uuids=(PERSON,),
                ),
            )
        ),
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    assert staged.payload is not None and staged.payload.effective_change_count == 0
    entry = inspect_draft(path, DraftInspectionRequest(limit=10)).payload.entries[0]  # type: ignore[union-attr]
    assert entry.proposed is None and not entry.has_effect
    report = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 100))
    assert report.payload is not None and not report.payload.clean
    assert activate_draft(path).outcome.status is OperationStatus.REJECTED

    created = apply_graph_change(
        path,
        GraphChangeRequest(1, (AssociatedDataUpsert(partial, "test.details", (PERSON,)),)),
    )
    assert created.resulting_revision == 2
    effective = _objects_from_state(read_state(path, DraftState()))[partial]
    assert isinstance(effective, AssociatedData) and effective.anchor_uuids == (PERSON,)
    assert validate_state(path, ValidationRequest(ValidationScope.DRAFT, 100)).payload.clean  # type: ignore[union-attr]


def test_unmaterializable_selector_uses_conclusive_staged_predicates(tmp_path: Path) -> None:
    path = _database(tmp_path)
    partial = "aeaeaeae-aeae-4eae-8eae-aeaeaeaeaeae"
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(AnchorUpsert(partial, display_name="Definitely staged"),)
        ),
    )

    def selected(expected):
        predicate = Predicate(
            DisplayNameField(), PredicateOperator.EQUAL, ScalarValue.text(expected)
        )
        selection = PatternSelection(
            10,
            (
                PatternNode(
                    "person", PatternNodeKind.ANCHOR, ("test.person",), predicates=(predicate,)
                ),
            ),
        )
        return query_graph(path, GraphQuery(selection, DraftState()))

    excluded = selected("Different")
    assert excluded.status is OperationStatus.ACCEPTED
    assert isinstance(excluded.payload, PatternQueryPayload) and not excluded.payload.matches
    possible = selected("Definitely staged")
    assert possible.status is OperationStatus.REJECTED
    assert possible.findings[0].code is FindingCode.MISSING


def test_unmaterializable_selector_uses_staged_property_set_and_remove(tmp_path: Path) -> None:
    path = _database(tmp_path)
    partial = "afafafaf-afaf-4faf-8faf-afafafafafaf"
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AssociatedDataUpsert(
                    partial,
                    "test.details",
                    set_properties=(("note", ScalarValue.text("known")),),
                ),
            )
        ),
    )

    def selected(operator, value=None):
        predicate = Predicate(PropertyField("note"), operator, value)
        selection = PatternSelection(
            10,
            (
                PatternNode(
                    "details",
                    PatternNodeKind.ASSOCIATED_DATA,
                    ("test.details",),
                    predicates=(predicate,),
                ),
            ),
        )
        return query_graph(path, GraphQuery(selection, DraftState()))

    assert (
        selected(PredicateOperator.EQUAL, ScalarValue.text("other")).status
        is OperationStatus.ACCEPTED
    )
    assert (
        selected(PredicateOperator.EQUAL, ScalarValue.text("known")).status
        is OperationStatus.REJECTED
    )
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(AssociatedDataUpsert(partial, remove_properties=("note",)),)
        ),
    )
    assert selected(PredicateOperator.PRESENT).status is OperationStatus.ACCEPTED
    assert selected(PredicateOperator.MISSING).status is OperationStatus.REJECTED


def test_accumulated_draft_paths_stream_complete_populations(tmp_path: Path, monkeypatch) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AnchorUpsert(PERSON, display_name="Draft Alice"),
                AnchorUpsert(PERSON_2, display_name="Draft Bob"),
            )
        ),
    )
    original_inspect = inspection_module.connect_database
    original_draft = draft_module.connect_database
    original_read = read_module.connect_database
    streamed_hash = False
    streamed_descriptors = False

    class GuardedCursor:
        def __init__(self, cursor, sql):
            self.cursor, self.sql = cursor, " ".join(sql.split()).lower()

        def __getattr__(self, name):
            return getattr(self.cursor, name)

        def __iter__(self):
            return iter(self.cursor)

        def fetchall(self):
            complete = (
                "from draft_graph_object_patch order by uuid" in self.sql
                or "from draft_definition_entry order by type_key" in self.sql
            )
            if complete:
                raise AssertionError("complete accumulated draft was fetched into Python")
            return self.cursor.fetchall()

    class GuardedConnection:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def execute(self, sql, parameters=()):
            return GuardedCursor(self.connection.execute(sql, parameters), sql)

    monkeypatch.setattr(
        inspection_module,
        "connect_database",
        lambda database_path: GuardedConnection(original_inspect(database_path)),
    )
    monkeypatch.setattr(
        draft_module,
        "connect_database",
        lambda database_path: GuardedConnection(original_draft(database_path)),
    )
    monkeypatch.setattr(
        read_module,
        "connect_database",
        lambda database_path, **kwargs: GuardedConnection(original_read(database_path, **kwargs)),
    )
    original_hash = draft_repository_module.ordered_values_hash

    def traced_hash(values):
        nonlocal streamed_hash
        first = values()
        assert not isinstance(first, tuple | list)
        streamed_hash = True
        return original_hash(values)

    monkeypatch.setattr(draft_repository_module, "ordered_values_hash", traced_hash)
    original_record_hash = activation_module.canonical_record_hash_members

    def traced_record_hash(
        previous, header, introduced_length, introduced, retired_length, retired
    ):
        nonlocal streamed_descriptors
        assert not isinstance(introduced, tuple | list)
        assert not isinstance(retired, tuple | list)
        streamed_descriptors = True
        return original_record_hash(
            previous,
            header,
            introduced_length,
            introduced,
            retired_length,
            retired,
        )

    monkeypatch.setattr(activation_module, "canonical_record_hash_members", traced_record_hash)
    assert inspect_draft(path, DraftInspectionRequest(limit=1)).payload.returned_count == 1  # type: ignore[union-attr]
    assert validate_state(path, ValidationRequest(ValidationScope.DRAFT, 1)).payload.clean  # type: ignore[union-attr]
    assert type_summary(path, DraftState()).status is OperationStatus.ACCEPTED
    assert activate_draft(path).outcome.status is OperationStatus.ACCEPTED
    assert streamed_hash and streamed_descriptors


def test_draft_type_summary_rejects_over_limit_before_definition_hydration(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    first = tuple(AnchorTypeDefinition(f"bulk.{index:04d}", "Bulk") for index in range(1_000))
    assert (
        change_draft(path, DraftChangeRequest(definition_upserts=first)).outcome.status
        is OperationStatus.ACCEPTED
    )
    assert (
        change_draft(
            path,
            DraftChangeRequest(definition_upserts=(AnchorTypeDefinition("bulk.extra", "Bulk"),)),
        ).outcome.status
        is OperationStatus.ACCEPTED
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("over-limit summary hydrated the complete definition population")

    monkeypatch.setattr(read_module, "load_draft_definitions", forbidden)
    result = type_summary(path, DraftState())
    assert result.status is OperationStatus.REJECTED
    assert result.findings[0].code is FindingCode.RESULT_LIMIT_EXCEEDED


def test_draft_type_summary_bounds_the_effective_key_set_after_removals(tmp_path: Path) -> None:
    path = tmp_path / "owner" / "vellis.db"
    definitions = tuple(AnchorTypeDefinition(f"bulk.{index:04d}", "Bulk") for index in range(1_000))
    initialize_with_definitions(path, definitions, recorded_at="2026-08-20T00:00:00Z")
    staged = change_draft(
        path,
        DraftChangeRequest(
            definition_upserts=(AnchorTypeDefinition("zzzz.later", "Later"),),
            definition_removals=("bulk.0000",),
        ),
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    selected = type_summary(path, DraftState())
    assert selected.status is OperationStatus.ACCEPTED
    assert selected.anchor_types is not None
    keys = tuple(value.type_key for value in selected.anchor_types)
    assert len(keys) == 1_000
    assert keys == tuple(sorted(keys))
    assert "bulk.0000" not in keys and "zzzz.later" in keys

    assert discard_draft(path).status is OperationStatus.ACCEPTED
    staged = change_draft(
        path,
        DraftChangeRequest(definition_upserts=(AnchorTypeDefinition("zzzz.later", "Later"),)),
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    rejected = type_summary(path, DraftState())
    assert rejected.status is OperationStatus.REJECTED
    assert rejected.findings[0].code is FindingCode.RESULT_LIMIT_EXCEEDED


def test_draft_type_inspect_excludes_superseded_live_neighborhood_members(tmp_path: Path) -> None:
    path = tmp_path / "owner" / "vellis.db"
    definitions = (
        AnchorTypeDefinition("test.a", "A"),
        AnchorTypeDefinition("test.b", "B"),
        AssociatedDataTypeDefinition(
            "test.data",
            "Data",
            ("test.a",),
            (),
            Cardinality(1),
            Cardinality(0),
        ),
        LinkTypeDefinition(
            "test.link",
            "Link",
            ("test.data",),
            ("test.b",),
            Cardinality(0),
            Cardinality(0),
        ),
    )
    initialize_with_definitions(path, definitions, recorded_at="2026-08-20T00:00:00Z")
    replacement = AssociatedDataTypeDefinition(
        "test.data",
        "Data",
        ("test.b",),
        (),
        Cardinality(1),
        Cardinality(0),
    )
    staged = change_draft(path, DraftChangeRequest(definition_upserts=(replacement,)))
    assert staged.outcome.status is OperationStatus.ACCEPTED
    old = type_inspect(path, ("test.a",), state_selection=DraftState())
    new = type_inspect(path, ("test.b",), state_selection=DraftState())
    assert old.status is OperationStatus.ACCEPTED
    assert new.status is OperationStatus.ACCEPTED
    assert old.neighborhoods is not None and not old.neighborhoods[0].associated_data_types
    assert old.neighborhoods[0].link_types == ()
    assert new.neighborhoods is not None
    assert tuple(value.type_key for value in new.neighborhoods[0].associated_data_types) == (
        "test.data",
    )
    assert tuple(value.type_key for value in new.neighborhoods[0].link_types) == ("test.link",)


def test_unknown_null_property_is_staged_then_reported_by_validation(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    staged = change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(AssociatedDataUpsert(DATA, set_properties=(("unknown", None),)),)
        ),
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    report = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 100))
    assert report.payload is not None and not report.payload.clean
    assert any(finding.code is FindingCode.UNKNOWN for finding in report.payload.findings)


def test_pattern_rejects_potential_unmaterializable_selector_without_uuid(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    partial = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    change_draft(
        path,
        DraftChangeRequest(object_upserts=(AnchorUpsert(partial, display_name="Partial"),)),
    )
    selection = PatternSelection(
        10,
        (PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),),
    )
    rejected = query_graph(path, GraphQuery(selection, DraftState()))
    assert rejected.status is OperationStatus.REJECTED
    assert rejected.findings[0].code is FindingCode.MISSING


def test_draft_pattern_uses_sql_max_plus_one_before_hydration(tmp_path: Path, monkeypatch) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Alice"),))
    )

    selected = False
    original = draft_read_module.select_pattern_bindings

    def traced(*args, **kwargs):
        nonlocal selected
        selected = True
        return original(*args, **kwargs)

    monkeypatch.setattr(draft_read_module, "select_pattern_bindings", traced)
    selection = PatternSelection(
        1,
        (PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),),
    )
    result = query_graph(path, GraphQuery(selection, DraftState()))
    assert selected
    assert result.status is OperationStatus.REJECTED
    assert result.findings[0].code is FindingCode.RESULT_LIMIT_EXCEEDED
    assert result.payload is None


def test_draft_pattern_fts_uses_effective_staged_text(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AssociatedDataUpsert(
                    DATA, set_properties=(("note", ScalarValue.text("Café draft phrase")),)
                ),
            )
        ),
    )
    predicate = Predicate(
        PropertyField("note"),
        PredicateOperator.PHRASE,
        text="cafe draft",
    )
    selection = PatternSelection(
        10,
        (
            PatternNode(
                "details",
                PatternNodeKind.ASSOCIATED_DATA,
                ("test.details",),
                predicates=(predicate,),
            ),
        ),
    )
    result = query_graph(path, GraphQuery(selection, DraftState()))
    assert result.status is OperationStatus.ACCEPTED
    assert result.payload.matches[0].bindings == (("details", DATA),)  # type: ignore[union-attr]


def test_draft_only_addition_has_no_system_until_activation(tmp_path: Path) -> None:
    path = _database(tmp_path)
    addition = "77777777-7777-4777-8777-777777777777"
    change_draft(
        path,
        DraftChangeRequest(object_upserts=(AnchorUpsert(addition, "test.person", "Draft only"),)),
    )
    query = GraphQuery(IdentitySelection((IdentityObjectSelection(addition),)), DraftState())
    proposed = query_graph(path, query).payload.objects[0]  # type: ignore[union-attr]
    assert proposed.system is None
    activated = activate_draft(path)
    assert activated.outcome.resulting_revision == 1
    live = _objects(path)[addition]
    assert live.system is not None
    assert (live.system.created_revision, live.system.last_changed_revision) == (1, 1)


def test_one_activation_reserves_all_new_graph_identities_before_dependents(tmp_path: Path) -> None:
    path = _database(tmp_path)
    link = "00000000-0000-4000-8000-000000000001"
    data = "11111111-0000-4000-8000-000000000001"
    group = "eeeeeeee-0000-4000-8000-000000000001"
    person = "ffffffff-0000-4000-8000-000000000001"
    staged = change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                LinkUpsert(link, "test.member", person, group),
                AssociatedDataUpsert(data, "test.details", (person,)),
                AnchorUpsert(group, "test.group", "Team"),
                AnchorUpsert(person, "test.person", "Alice"),
            )
        ),
    )

    assert staged.outcome.status is OperationStatus.ACCEPTED
    assessment = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 100))
    assert assessment.payload is not None and assessment.payload.clean is True
    activated = activate_draft(path)
    assert activated.outcome.status is OperationStatus.ACCEPTED
    assert activated.outcome.resulting_revision == 1
    assert set(_objects(path)) == {link, data, group, person}


def test_one_activation_reserves_all_new_type_keys_before_dependencies(tmp_path: Path) -> None:
    path = _database(tmp_path)
    dependent = AssociatedDataTypeDefinition(
        "aaa.details",
        "Lexically first dependent",
        ("zzz.anchor",),
        (),
        Cardinality(1, 1),
        Cardinality(0),
    )
    anchor = AnchorTypeDefinition("zzz.anchor", "Lexically later anchor")
    changed = change_draft(
        path,
        DraftChangeRequest(definition_upserts=(dependent, anchor)),
    )
    assert changed.outcome.status is OperationStatus.ACCEPTED
    validated = validate_state(path, ValidationRequest(ValidationScope.DRAFT, limit=1_000))
    assert validated.payload is not None and validated.payload.clean is True

    activated = activate_draft(path)

    assert activated.outcome.status is OperationStatus.ACCEPTED
    assert activated.outcome.resulting_revision == 1
    assert {value.type_key for value in read_state(path).definitions} >= {
        "aaa.details",
        "zzz.anchor",
    }


def test_draft_reactivation_preserves_original_creation_metadata(tmp_path: Path) -> None:
    path = _database(tmp_path)
    retired = "88888888-8888-4888-8888-888888888888"
    assert (
        apply_graph_change(
            path, GraphChangeRequest(0, (AnchorUpsert(retired, "test.person", "First"),))
        ).resulting_revision
        == 1
    )
    assert (
        apply_graph_change(path, GraphChangeRequest(1, remove_uuids=(retired,))).resulting_revision
        == 2
    )
    change_draft(
        path,
        DraftChangeRequest(object_upserts=(AnchorUpsert(retired, "test.person", "Returned"),)),
    )
    draft_value = query_graph(
        path,
        GraphQuery(IdentitySelection((IdentityObjectSelection(retired),)), DraftState()),
    ).payload.objects[0]  # type: ignore[union-attr]
    assert draft_value.system is None
    assert activate_draft(path).outcome.resulting_revision == 3
    live = _objects(path)[retired]
    assert live.system is not None
    assert (live.system.created_revision, live.system.last_changed_revision) == (1, 3)
    assert audit_database(path).clean


def test_repeated_draft_edits_merge_tombstone_restart_and_unstage(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="One"),))
    )
    change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Two"),))
    )
    change_draft(path, DraftChangeRequest(object_removals=(PERSON,)))
    change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Restart"),))
    )
    inspected = inspect_draft(path, DraftInspectionRequest(limit=10))
    assert inspected.payload is not None
    assert inspected.payload.counts.raw_entry_count == 1
    assert inspected.payload.entries[0].proposed.display_name == "Restart"  # type: ignore[union-attr]
    cleared = change_draft(path, DraftChangeRequest(unstage_object_uuids=(PERSON,)))
    assert cleared.payload == cleared.payload.__class__(False, 0, 0)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("uuid", "upsert", "category"),
    (
        (
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            AnchorUpsert("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "test.person", "Draft"),
            DraftCategory.ANCHORS,
        ),
        (
            "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            AssociatedDataUpsert("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "test.details", (PERSON,)),
            DraftCategory.ASSOCIATED_DATA,
        ),
        (
            "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            LinkUpsert("dddddddd-dddd-4ddd-8ddd-dddddddddddd", "test.member", PERSON, GROUP),
            DraftCategory.LINKS,
        ),
    ),
)
def test_removing_never_live_draft_addition_stages_tombstone(
    tmp_path: Path, uuid, upsert, category
) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(path, DraftChangeRequest(object_upserts=(upsert,)))
    changed = change_draft(path, DraftChangeRequest(object_removals=(uuid,)))
    assert changed.payload is not None
    assert (changed.payload.raw_entry_count, changed.payload.effective_change_count) == (1, 0)
    entry = inspect_draft(path, DraftInspectionRequest(limit=10)).payload.entries[0]  # type: ignore[union-attr]
    assert (entry.category, entry.operation, entry.staged) == (
        category,
        DraftOperation.REMOVE,
        {"remove": True},
    )
    selected = query_graph(
        path, GraphQuery(IdentitySelection((IdentityObjectSelection(uuid),)), DraftState())
    )
    assert selected.payload.missing_uuids == (uuid,)  # type: ignore[union-attr]


def test_inspection_exposes_complete_raw_definition_replacement_without_system(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    replacement = AnchorTypeDefinition("test.person", "Replacement meaning")
    change_draft(path, DraftChangeRequest(definition_upserts=(replacement,)))
    entry = inspect_draft(path, DraftInspectionRequest(limit=10)).payload.entries[0]  # type: ignore[union-attr]
    assert entry.operation is DraftOperation.REPLACE
    assert entry.staged == replacement
    assert isinstance(entry.staged, AnchorTypeDefinition)
    assert entry.staged.system is None


def test_inspection_exposes_precise_raw_object_field_operations(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AssociatedDataUpsert(
                    DATA,
                    type_key="test.details",
                    add_anchor_uuids=(PERSON_2,),
                    remove_anchor_uuids=(PERSON,),
                    set_properties=(("maybe", None),),
                    remove_properties=("note",),
                ),
            )
        ),
    )
    entry = inspect_draft(path, DraftInspectionRequest(limit=10)).payload.entries[0]  # type: ignore[union-attr]
    assert entry.staged == {
        "typeKey": "test.details",
        "addAnchorUuids": [PERSON_2],
        "removeAnchorUuids": [PERSON],
        "setProperties": {"maybe": None},
        "removeProperties": ["note"],
    }


def test_inspection_pages_and_expires_on_live_or_draft_change(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AnchorUpsert(PERSON, display_name="Draft A"),
                AnchorUpsert(PERSON_2, display_name="Draft B"),
            )
        ),
    )
    first = inspect_draft(path, DraftInspectionRequest(limit=1))
    assert first.payload is not None and first.payload.cursor is not None
    cursor = first.payload.cursor
    second = inspect_draft(path, DraftInspectionRequest(cursor=cursor))
    assert second.payload is not None and second.payload.returned_count == 1

    fresh = inspect_draft(path, DraftInspectionRequest(limit=1))
    cursor = fresh.payload.cursor  # type: ignore[union-attr]
    apply_graph_change(path, GraphChangeRequest(1, (AnchorUpsert(GROUP, display_name="Changed"),)))
    expired = inspect_draft(path, DraftInspectionRequest(cursor=cursor))
    assert expired.outcome.status is OperationStatus.REJECTED
    assert expired.outcome.findings[0].code is FindingCode.EXPIRED_CURSOR


def test_inspection_non_ascii_cursor_is_an_expired_domain_result(tmp_path: Path) -> None:
    path = _database(tmp_path)
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AnchorUpsert(PERSON, display_name="Draft A"),
                AnchorUpsert(PERSON_2, display_name="Draft B"),
            )
        ),
    )
    first = inspect_draft(path, DraftInspectionRequest(limit=1))
    assert first.payload is not None and first.payload.cursor is not None

    expired = inspect_draft(path, DraftInspectionRequest(cursor="opaque-雪-💡"))
    assert expired.outcome.status is OperationStatus.REJECTED
    assert expired.outcome.findings[0].code is FindingCode.EXPIRED_CURSOR


def test_validation_is_accepted_when_dirty_and_cursor_expires(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(path, DraftChangeRequest(definition_removals=("test.person",)))
    report = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 1))
    assert report.outcome.status is OperationStatus.ACCEPTED
    assert report.payload is not None and not report.payload.clean
    assert report.payload.cursor is not None
    cursor = report.payload.cursor
    change_draft(path, DraftChangeRequest(unstage_definition_keys=("test.person",)))
    expired = validate_state(path, ValidationRequest(ValidationScope.DRAFT, cursor=cursor))
    assert expired.outcome.status is OperationStatus.REJECTED
    assert expired.outcome.findings[0].code is FindingCode.EXPIRED_CURSOR


@pytest.mark.parametrize("scope", (ValidationScope.CURRENT, ValidationScope.DRAFT))
def test_validation_non_ascii_cursor_is_an_expired_domain_result(
    tmp_path: Path, scope: ValidationScope
) -> None:
    path = _database(tmp_path)
    if scope is ValidationScope.DRAFT:
        change_draft(path, DraftChangeRequest(definition_removals=("test.person",)))

    expired = validate_state(path, ValidationRequest(scope, cursor="opaque-雪-💡"))
    assert expired.outcome.status is OperationStatus.REJECTED
    assert expired.outcome.findings[0].code is FindingCode.EXPIRED_CURSOR


def test_validation_continuation_reuses_page_limit_and_draft_counts(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(path, DraftChangeRequest(definition_removals=("test.person",)))
    first = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 1))
    assert first.payload is not None and first.payload.cursor is not None
    assert first.payload.raw_draft_entry_count == 1
    cursor = first.payload.cursor
    second = validate_state(path, ValidationRequest(ValidationScope.DRAFT, cursor=cursor))
    assert second.payload is not None
    assert len(second.payload.findings) == 1
    assert second.payload.raw_draft_entry_count == 1
    assert second.payload.effective_draft_change_count == 1


def test_activation_revalidates_invalid_valid_and_redundant_drafts(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(path, DraftChangeRequest(definition_removals=("test.person",)))
    invalid = activate_draft(path, finding_limit=1)
    assert invalid.outcome.status is OperationStatus.REJECTED
    assert read_state(path).evaluated_revision == 1
    assert inspect_draft(path, DraftInspectionRequest(limit=10)).payload.counts.draft_present  # type: ignore[union-attr]

    change_draft(path, DraftChangeRequest(unstage_definition_keys=("test.person",)))
    redundant = change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Alice"),))
    )
    assert redundant.payload is not None and redundant.payload.effective_change_count == 0
    cleared = activate_draft(path)
    assert cleared.outcome.status is OperationStatus.ACCEPTED
    assert cleared.outcome.resulting_revision is None
    assert read_state(path).evaluated_revision == 1


def test_draft_discard_and_absence_have_no_canonical_effect(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),))
    )
    assert discard_draft(path).status is OperationStatus.ACCEPTED
    assert discard_draft(path).status is OperationStatus.ACCEPTED
    assert read_state(path).evaluated_revision == 1


def test_draft_discovery_and_pattern_query_use_effective_definitions(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    replacement = AnchorTypeDefinition("test.person", "Draft person meaning")
    change_draft(
        path,
        DraftChangeRequest(
            definition_upserts=(replacement,),
            object_upserts=(AnchorUpsert(PERSON, display_name="Draft Alice"),),
        ),
    )
    summary = type_summary(path, DraftState())
    assert any(
        value.type_key == "test.person" and value.description == "Draft person meaning"
        for value in summary.anchor_types or ()
    )
    inspected = type_inspect(path, ("test.person",), state_selection=DraftState())
    assert inspected.neighborhoods is not None
    assert inspected.neighborhoods[0].anchor_type.description == "Draft person meaning"
    pattern = PatternSelection(
        10, (PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),)
    )
    result = query_graph(path, GraphQuery(pattern, DraftState()))
    assert result.payload.matches[0].bindings == (("person", PERSON),)  # type: ignore[union-attr]
    assert result.payload.objects[0].display_name == "Draft Alice"  # type: ignore[union-attr]


def test_activation_definition_replacement_updates_only_definition_metadata(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    before = _objects(path)[PERSON]
    replacement = AnchorTypeDefinition("test.person", "Changed description")
    change_draft(path, DraftChangeRequest(definition_upserts=(replacement,)))
    result = activate_draft(path)
    assert result.outcome.resulting_revision == 2
    definition = next(
        value for value in read_state(path).definitions if value.type_key == "test.person"
    )
    assert definition.system is not None
    assert (definition.system.created_revision, definition.system.last_changed_revision) == (0, 2)
    after = _objects(path)[PERSON]
    assert after.system == before.system
    assert audit_database(path).clean


def test_property_selection_on_draft_preserves_absence_and_unseen_fields(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AssociatedDataUpsert(DATA, set_properties=(("maybe", ScalarValue.text("draft")),)),
            )
        ),
    )
    selection = IdentitySelection((IdentityObjectSelection(DATA, PropertySelection(("maybe",))),))
    result = query_graph(path, GraphQuery(selection, DraftState()))
    value = result.payload.objects[0]  # type: ignore[union-attr]
    assert value.properties == (("maybe", ScalarValue.text("draft")),)
    live = _objects(path)[DATA]
    assert isinstance(live, AssociatedData)
    assert live.properties == (("note", ScalarValue.text("original")),)


def test_pattern_preflight_has_current_and_effective_draft_parity(tmp_path: Path) -> None:
    path = tmp_path / "owner" / "vellis.db"
    project = "bcbcbcbc-bcbc-4cbc-8cbc-bcbcbcbcbcbc"
    initialize_with_definitions(
        path,
        (*_definitions(), AnchorTypeDefinition("test.project", "Project")),
        recorded_at="2026-08-20T00:00:00Z",
    )
    created = GraphChangeRequest(
        0,
        (
            AnchorUpsert(PERSON, "test.person", "Alice"),
            AnchorUpsert(GROUP, "test.group", "Team"),
            AnchorUpsert(project, "test.project", "Project"),
            AssociatedDataUpsert(DATA, "test.details", (PERSON,)),
            LinkUpsert(LINK, "test.member", PERSON, GROUP),
        ),
    )
    assert apply_graph_change(path, created).resulting_revision == 1
    change_draft(
        path,
        DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Alice"),)),
    )
    cases = (
        PatternSelection(
            10,
            (PatternNode("wrongKind", PatternNodeKind.ASSOCIATED_DATA, uuids=(PERSON,)),),
        ),
        PatternSelection(
            10,
            (
                PatternNode("source", PatternNodeKind.ANCHOR, ("test.group",)),
                PatternNode("target", PatternNodeKind.ANCHOR, ("test.person",)),
            ),
            links=(PatternLink("edge", "source", "target", ("test.member",)),),
        ),
        PatternSelection(
            10,
            (
                PatternNode("project", PatternNodeKind.ANCHOR, ("test.project",)),
                PatternNode("details", PatternNodeKind.ASSOCIATED_DATA, ("test.details",)),
            ),
            direct_associations=(DirectAssociation("project", "details"),),
        ),
        PatternSelection(
            10,
            (
                PatternNode("source", PatternNodeKind.ANCHOR, ("test.person",)),
                PatternNode("target", PatternNodeKind.ANCHOR, ("test.group",)),
            ),
            links=(PatternLink("edge", "source", "target"),),
        ),
        PatternSelection(
            10,
            (
                PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),
                PatternNode("details", PatternNodeKind.ASSOCIATED_DATA, ("test.details",)),
            ),
            direct_associations=(DirectAssociation("person", "details"),),
        ),
    )
    for selection in cases:
        current = query_graph(path, GraphQuery(selection))
        draft = query_graph(path, GraphQuery(selection, DraftState()))
        assert draft.status is current.status
        assert tuple(value.code for value in draft.findings) == tuple(
            value.code for value in current.findings
        )
        if current.status is OperationStatus.ACCEPTED:
            assert isinstance(current.payload, PatternQueryPayload)
            assert isinstance(draft.payload, PatternQueryPayload)
            assert draft.payload.matches == current.payload.matches


def test_invalid_draft_pattern_rejects_before_graph_property_or_search_overlay(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    _seed(path)
    staged = change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),))
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    cases = (
        PatternSelection(
            10,
            (
                PatternNode(
                    "data",
                    PatternNodeKind.ASSOCIATED_DATA,
                    predicates=(
                        Predicate(
                            PropertyField("note"),
                            PredicateOperator.ALL_TERMS,
                            terms=("original",),
                        ),
                    ),
                ),
            ),
        ),
        PatternSelection(
            10,
            (
                PatternNode(
                    "data",
                    PatternNodeKind.ASSOCIATED_DATA,
                    ("test.details",),
                    predicates=(
                        Predicate(
                            PropertyField("unknown"),
                            PredicateOperator.EQUAL,
                            ScalarValue.text("value"),
                        ),
                    ),
                ),
            ),
        ),
        PatternSelection(
            10,
            (PatternNode("person", PatternNodeKind.ANCHOR, ("test.unknown",)),),
        ),
        PatternSelection(
            10,
            (
                PatternNode(
                    "data",
                    PatternNodeKind.ASSOCIATED_DATA,
                    ("test.details",),
                    predicates=(
                        Predicate(
                            PropertyField("note"),
                            PredicateOperator.ALL_TERMS,
                            terms=("two terms",),
                        ),
                    ),
                ),
            ),
        ),
        PatternSelection(
            10,
            (
                PatternNode(
                    "data",
                    PatternNodeKind.ASSOCIATED_DATA,
                    ("test.details",),
                    predicates=(
                        Predicate(
                            PropertyField("note"),
                            PredicateOperator.PHRASE,
                            text="---",
                        ),
                    ),
                ),
            ),
        ),
        PatternSelection(
            10,
            (
                PatternNode(
                    "data",
                    PatternNodeKind.ASSOCIATED_DATA,
                    ("test.details",),
                    predicates=(
                        Predicate(
                            PropertyField("note"),
                            PredicateOperator.REGEX,
                            text="(",
                        ),
                    ),
                ),
            ),
        ),
    )
    current_results = tuple(query_graph(path, GraphQuery(selection)) for selection in cases)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("invalid draft query installed graph/property/search overlay")

    monkeypatch.setattr(read_module, "install_draft_graph_overlay", forbidden)
    for selection, current in zip(cases, current_results, strict=True):
        draft = query_graph(path, GraphQuery(selection, DraftState()))
        assert current.status is OperationStatus.REJECTED
        assert draft.status is current.status
        assert tuple((value.code, value.path) for value in draft.findings) == tuple(
            (value.code, value.path) for value in current.findings
        )


def test_current_and_draft_identity_routes_preflight_before_value_loading(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    _seed(path)
    staged = change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),))
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    invalid = (
        IdentitySelection((IdentityObjectSelection(PERSON), IdentityObjectSelection(PERSON))),
        IdentitySelection((IdentityObjectSelection(DATA, PropertySelection(("note", "note"))),)),
        IdentitySelection((IdentityObjectSelection(PERSON, PropertySelection(("note",))),)),
    )
    current_results = tuple(query_graph(path, GraphQuery(selection)) for selection in invalid)

    original_load = read_module.load_graph_objects

    def forbidden(*_args, **_kwargs):
        raise AssertionError("invalid draft identity request loaded object values")

    monkeypatch.setattr(read_module, "load_graph_objects", forbidden)
    for selection, current in zip(invalid, current_results, strict=True):
        draft = query_graph(path, GraphQuery(selection, DraftState()))
        assert current.status is OperationStatus.REJECTED
        assert draft.status is current.status
        assert tuple((value.code, value.path) for value in draft.findings) == tuple(
            (value.code, value.path) for value in current.findings
        )
    monkeypatch.setattr(read_module, "load_graph_objects", original_load)

    missing = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    valid_identities = (
        IdentitySelection((IdentityObjectSelection(PERSON),)),
        IdentitySelection((IdentityObjectSelection(missing, PropertySelection(("notDefined",))),)),
    )
    for selection in valid_identities:
        current = query_graph(path, GraphQuery(selection))
        draft = query_graph(path, GraphQuery(selection, DraftState()))
        assert current.status is OperationStatus.ACCEPTED
        assert draft.status is current.status
        assert draft.payload.found_uuids == current.payload.found_uuids  # type: ignore[union-attr]
        assert draft.payload.missing_uuids == current.payload.missing_uuids  # type: ignore[union-attr]

    over_limit = PatternSelection(
        1, (PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),)
    )
    current = query_graph(path, GraphQuery(over_limit))
    draft = query_graph(path, GraphQuery(over_limit, DraftState()))
    assert current.status is OperationStatus.REJECTED
    assert draft.status is current.status
    assert current.findings[0].code is FindingCode.RESULT_LIMIT_EXCEEDED
    assert draft.findings[0].code is current.findings[0].code


def test_draft_single_node_does_not_load_permitting_relationship_definitions(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "owner" / "vellis.db"
    live_data = tuple(
        AssociatedDataTypeDefinition(
            f"live.data.{index:03d}",
            "Data",
            ("test.person",),
            (),
            Cardinality(1),
            Cardinality(0),
        )
        for index in range(60)
    )
    live_links = tuple(
        LinkTypeDefinition(
            f"live.link.{index:03d}",
            "Link",
            ("test.person",),
            ("test.person",),
            Cardinality(0),
            Cardinality(0),
        )
        for index in range(60)
    )
    initialize_with_definitions(
        path,
        (AnchorTypeDefinition("test.person", "Person"), *live_data, *live_links),
        recorded_at="2026-08-20T00:00:00Z",
    )
    staged_data = tuple(
        AssociatedDataTypeDefinition(
            f"staged.data.{index:03d}",
            "Data",
            ("test.person",),
            (),
            Cardinality(1),
            Cardinality(0),
        )
        for index in range(60)
    )
    staged_links = tuple(
        LinkTypeDefinition(
            f"staged.link.{index:03d}",
            "Link",
            ("test.person",),
            ("test.person",),
            Cardinality(0),
            Cardinality(0),
        )
        for index in range(60)
    )
    staged = change_draft(
        path, DraftChangeRequest(definition_upserts=(*staged_data, *staged_links))
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED

    loaded_keys = []
    original = read_module.load_definitions

    def traced(connection, state, type_keys=None):
        loaded_keys.append(type_keys)
        return original(connection, state, type_keys)

    monkeypatch.setattr(read_module, "load_definitions", traced)
    selection = PatternSelection(
        10, (PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),)
    )
    for state in (None, DraftState()):
        loaded_keys.clear()
        result = query_graph(path, GraphQuery(selection, state))
        assert result.status is OperationStatus.ACCEPTED
        assert loaded_keys
    assert all(keys == ("test.person",) for keys in loaded_keys)


@pytest.mark.parametrize("draft", (False, True))
def test_untyped_relationship_preflight_streams_witnesses_and_rejects_incompatibility(
    tmp_path: Path, monkeypatch, draft: bool
) -> None:
    path = tmp_path / "owner" / "vellis.db"
    definitions = (
        AnchorTypeDefinition("test.group", "Group"),
        AnchorTypeDefinition("test.person", "Person"),
        AnchorTypeDefinition("test.project", "Project"),
        AssociatedDataTypeDefinition(
            "a.data.compatible",
            "Compatible data",
            ("test.person",),
            (),
            Cardinality(1),
            Cardinality(0),
        ),
        AssociatedDataTypeDefinition(
            "z.data.other",
            "Other data",
            ("test.group",),
            (),
            Cardinality(1),
            Cardinality(0),
        ),
        LinkTypeDefinition(
            "a.link.compatible",
            "Compatible link",
            ("test.person",),
            ("test.group",),
            Cardinality(0),
            Cardinality(0),
        ),
        LinkTypeDefinition(
            "z.link.other",
            "Other link",
            ("test.group",),
            ("test.person",),
            Cardinality(0),
            Cardinality(0),
        ),
    )
    initialize_with_definitions(path, definitions, recorded_at="2026-08-20T00:00:00Z")
    state = None
    if draft:
        staged = change_draft(
            path,
            DraftChangeRequest(definition_upserts=(AnchorTypeDefinition("test.draft", "Draft"),)),
        )
        assert staged.outcome.status is OperationStatus.ACCEPTED
        state = DraftState()

    loaded_relationships = []
    original = read_module.load_definitions

    def traced(connection, resolved, type_keys=None):
        if type_keys and any(".data." in key or ".link." in key for key in type_keys):
            loaded_relationships.append(type_keys)
        return original(connection, resolved, type_keys)

    monkeypatch.setattr(read_module, "load_definitions", traced)
    valid_link = PatternSelection(
        10,
        (
            PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),
            PatternNode("group", PatternNodeKind.ANCHOR, ("test.group",)),
        ),
        links=(PatternLink("edge", "person", "group"),),
    )
    valid_direct = PatternSelection(
        10,
        (
            PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),
            PatternNode("data", PatternNodeKind.ASSOCIATED_DATA),
        ),
        direct_associations=(DirectAssociation("person", "data"),),
    )
    for selection in (valid_link, valid_direct):
        loaded_relationships.clear()
        result = query_graph(path, GraphQuery(selection, state))
        assert result.status is OperationStatus.ACCEPTED
        assert len(loaded_relationships) == 1
        assert len(loaded_relationships[0]) == 1

    invalid_link = PatternSelection(
        10,
        (
            PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),
            PatternNode("project", PatternNodeKind.ANCHOR, ("test.project",)),
        ),
        links=(PatternLink("edge", "person", "project"),),
    )
    invalid_direct = PatternSelection(
        10,
        (
            PatternNode("project", PatternNodeKind.ANCHOR, ("test.project",)),
            PatternNode("data", PatternNodeKind.ASSOCIATED_DATA),
        ),
        direct_associations=(DirectAssociation("project", "data"),),
    )
    for selection in (invalid_link, invalid_direct):
        loaded_relationships.clear()
        result = query_graph(path, GraphQuery(selection, state))
        assert result.status is OperationStatus.REJECTED
        assert any(value.code is FindingCode.KIND_MISMATCH for value in result.findings)
        assert loaded_relationships
        assert all(len(keys) == 1 for keys in loaded_relationships)


def test_unmaterializable_null_predicates_match_sql_null_semantics(tmp_path: Path) -> None:
    path = _database(tmp_path)
    partial = "bdbdbdbd-bdbd-4dbd-8dbd-bdbdbdbdbdbd"
    change_draft(
        path,
        DraftChangeRequest(
            object_upserts=(
                AssociatedDataUpsert(
                    partial,
                    "test.details",
                    set_properties=(("maybe", None),),
                ),
            )
        ),
    )
    text = ScalarValue.text("value")
    cases = (
        (Predicate(PropertyField("maybe"), PredicateOperator.PRESENT), True),
        (Predicate(PropertyField("maybe"), PredicateOperator.MISSING), False),
        (Predicate(PropertyField("maybe"), PredicateOperator.IS_NULL), True),
        (Predicate(PropertyField("maybe"), PredicateOperator.IS_NOT_NULL), False),
        (Predicate(PropertyField("maybe"), PredicateOperator.EQUAL, text), False),
        (Predicate(PropertyField("maybe"), PredicateOperator.NOT_EQUAL, text), False),
        (Predicate(PropertyField("maybe"), PredicateOperator.LESS_THAN, text), False),
        (
            Predicate(
                PropertyField("maybe"),
                PredicateOperator.ANY_OF,
                values=(None, text),
            ),
            True,
        ),
        (
            Predicate(PropertyField("maybe"), PredicateOperator.ANY_OF, values=(text,)),
            False,
        ),
    )
    for predicate, could_match in cases:
        selection = PatternSelection(
            10,
            (
                PatternNode(
                    "partial",
                    PatternNodeKind.ASSOCIATED_DATA,
                    ("test.details",),
                    (partial,),
                    (predicate,),
                ),
            ),
        )
        result = query_graph(path, GraphQuery(selection, DraftState()))
        assert (result.status is OperationStatus.REJECTED) is could_match


def test_unstaged_property_on_unmaterializable_object_remains_unknown(tmp_path: Path) -> None:
    path = _database(tmp_path)
    partial = "bebebebe-bebe-4ebe-8ebe-bebebebebebe"
    change_draft(
        path,
        DraftChangeRequest(object_upserts=(AssociatedDataUpsert(partial, "test.details"),)),
    )
    predicates = (
        Predicate(PropertyField("maybe"), PredicateOperator.PRESENT),
        Predicate(PropertyField("maybe"), PredicateOperator.MISSING),
        Predicate(PropertyField("maybe"), PredicateOperator.IS_NULL),
        Predicate(PropertyField("maybe"), PredicateOperator.IS_NOT_NULL),
        Predicate(PropertyField("maybe"), PredicateOperator.EQUAL, ScalarValue.text("value")),
    )
    for predicate in predicates:
        selection = PatternSelection(
            10,
            (
                PatternNode(
                    "partial",
                    PatternNodeKind.ASSOCIATED_DATA,
                    ("test.details",),
                    (partial,),
                    (predicate,),
                ),
            ),
        )
        result = query_graph(path, GraphQuery(selection, DraftState()))
        assert result.status is OperationStatus.REJECTED
        assert result.findings[0].code is FindingCode.MISSING
