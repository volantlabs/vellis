from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset
from apps.rtg_knowledge_graph.onboarding import config_for_data_dir
from apps.rtg_knowledge_graph.starter_schema import (
    VellisStartupFailed,
    load_starter_schema_bundle,
    prepare_controller,
)
from components.rtg.change_validation import DeterministicRtgChangeValidator
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import InProcessRtgController
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.migration import InMemoryRtgMigration
from components.rtg.query import SimpleRtgQueryEngine
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgSchemaDefinition,
)
from components.storage.json_file.implementation import LocalJsonFileStorage
from components.storage.sql import SqliteStorage


def test_everyday_life_bundle_is_exact_schema_only_and_deterministic() -> None:
    first = load_starter_schema_bundle()
    second = load_starter_schema_bundle()
    assert first == second
    assert first["ontology_id"] == "ontology.vellis.everyday_life"
    assert first["graph_objects"] == []
    UUID(first["bootstrap_migration_id"])

    writes = first["knowledge_changes"]["schema_changes"]["definition_writes"]
    definitions = [write["definition"] for write in writes]
    assert len(definitions) == 33
    assert {item["type_key"] for item in definitions if item["kind"] == "anchor"} == {
        "Person",
        "Group",
        "Area",
        "Goal",
        "Project",
        "Task",
        "Event",
        "Routine",
        "Decision",
        "Note",
        "Resource",
        "Place",
    }
    assert {item["type_key"] for item in definitions if item["kind"] == "link"} == {
        "belongs_to",
        "supports",
        "responsible_for",
        "member_of",
        "involves",
        "located_at",
        "documents",
        "mentions",
        "depends_on",
    }
    facts = {
        item["type_key"]: item["payload"]["properties"]
        for item in definitions
        if item["kind"] == "data_object"
    }
    expected_fields = {
        "PersonFacts": ("name", "relationship", "preferred_contact", "notes"),
        "GroupFacts": ("name", "kind", "description"),
        "AreaFacts": ("title", "domain", "focus", "active"),
        "GoalFacts": (
            "title",
            "domain",
            "status",
            "priority",
            "target_date",
            "desired_outcome",
        ),
        "ProjectFacts": (
            "title",
            "domain",
            "status",
            "priority",
            "desired_outcome",
            "next_review",
        ),
        "TaskFacts": ("title", "domain", "status", "priority", "due", "context"),
        "EventFacts": ("title", "domain", "status", "start", "end", "summary"),
        "RoutineFacts": ("title", "domain", "cadence", "active", "next_due", "context"),
        "DecisionFacts": ("title", "domain", "status", "decided_on", "rationale"),
        "NoteFacts": ("title", "domain", "topic", "summary", "captured_at"),
        "ResourceFacts": ("title", "domain", "kind", "locator", "summary"),
        "PlaceFacts": ("name", "kind", "address", "notes"),
    }
    assert {key: set(properties) for key, properties in facts.items()} == {
        key: set(properties) for key, properties in expected_fields.items()
    }
    all_anchors = [
        "Person",
        "Group",
        "Area",
        "Goal",
        "Project",
        "Task",
        "Event",
        "Routine",
        "Decision",
        "Note",
        "Resource",
        "Place",
    ]
    links = {
        item["type_key"]: (
            item["payload"]["allowed_source_types"],
            item["payload"]["allowed_target_types"],
        )
        for item in definitions
        if item["kind"] == "link"
    }
    assert links == {
        "belongs_to": (
            ["Goal", "Project", "Task", "Event", "Routine", "Decision", "Note", "Resource"],
            ["Area"],
        ),
        "supports": (
            ["Project", "Task", "Event", "Routine", "Decision", "Note", "Resource"],
            ["Goal", "Project"],
        ),
        "responsible_for": (
            ["Person", "Group"],
            ["Area", "Goal", "Project", "Task", "Event", "Routine"],
        ),
        "member_of": (["Person"], ["Group"]),
        "involves": (
            ["Goal", "Project", "Task", "Event", "Routine", "Decision"],
            ["Person", "Group"],
        ),
        "located_at": (["Task", "Event", "Routine", "Group"], ["Place"]),
        "documents": (["Note", "Resource"], all_anchors),
        "mentions": (["Note"], all_anchors),
        "depends_on": (["Goal", "Project", "Task"], ["Goal", "Project", "Task"]),
    }
    for definition in definitions:
        UUID(definition["uuid"])
        assert definition["system"] == {"live": False}
        if definition["kind"] == "data_object":
            required = [
                key
                for key, rule in definition["payload"]["properties"].items()
                if rule["required"]
            ]
            assert required in (["name"], ["title"])


def test_everyday_life_ontology_install_is_idempotent_and_replayable(tmp_path: Path) -> None:
    config = config_for_data_dir(tmp_path / "data")
    first = build_app(config)
    installed = first.prepare()
    assert installed.status == "installed"
    assert first.controller.get_system_state().live_schema_counts.total == 33

    toolset = RtgMcpToolset(first.controller, installed)
    created = toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "person-alex"},
                "type": "Person",
                "display_name": "Alex",
                "facts": [{"type": "PersonFacts", "properties": {"name": "Alex"}}],
            }
        ]
    )
    assert created["ok"] is True
    assert first.controller.get_system_state().state_classification == "populated"

    restarted = build_app(config)
    replayed = restarted.prepare()
    assert replayed.status == "installed"
    assert replayed.recovery == "ledger_replayed"
    state = restarted.controller.get_system_state()
    assert state.live_schema_counts.total == 33
    assert state.state_classification == "populated"

    repeated = restarted.prepare()
    assert repeated.status == "installed"
    assert restarted.controller.get_system_state().live_schema_counts.total == 33


def test_custom_schema_is_preserved_and_not_overlaid(tmp_path: Path) -> None:
    schema = InMemoryRtgSchema.empty()
    custom_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=custom_id,
            kind="anchor",
            type_key="CustomThing",
            description="Existing custom schema.",
            payload=RtgAnchorSchemaPayload(),
            system={"live": True},
        )
    )
    controller = _controller(tmp_path, schema)
    status = prepare_controller(controller)
    assert status.status == "custom"
    snapshot = controller.export_system_snapshot()
    assert len(snapshot.schema.definitions) == 1
    assert snapshot.schema.definitions[0]["type_key"] == "CustomThing"


def test_installed_ontology_can_be_extended_without_bootstrap_overwrite(tmp_path: Path) -> None:
    composition = build_app(config_for_data_dir(tmp_path / "data"))
    installed = composition.prepare()
    toolset = RtgMcpToolset(composition.controller, installed)
    staged = toolset.rtg_stage_schema_migration(
        migration_id="everyday-life-extension",
        description="Add a user-approved extension type.",
        schema_definitions=[
            {
                "kind": "anchor",
                "type_key": "UserExtension",
                "description": "An approved application extension.",
                "payload": {"required_data_types": []},
            }
        ],
    )
    assert staged["ok"] is True
    assert toolset.rtg_apply_migration_cutover("everyday-life-extension")["ok"] is True

    repeated = composition.prepare()
    assert repeated.status == "installed"
    assert composition.controller.get_system_state().live_schema_counts.total == 34


@pytest.mark.parametrize("collision", ["identity", "type_key"])
def test_starter_collision_fails_without_partial_effects(
    tmp_path: Path, collision: str
) -> None:
    bundle = load_starter_schema_bundle()
    first_definition = bundle["knowledge_changes"]["schema_changes"]["definition_writes"][0][
        "definition"
    ]
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=(
                UUID(first_definition["uuid"])
                if collision == "identity"
                else UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
            ),
            kind="anchor",
            type_key=("ConflictingPerson" if collision == "identity" else "Person"),
            description="Conflicts with a reserved starter identity.",
            payload=RtgAnchorSchemaPayload(),
            system={"live": True},
        )
    )
    controller = _controller(tmp_path, schema)
    before = controller.export_system_snapshot()
    with pytest.raises(VellisStartupFailed, match="collides"):
        prepare_controller(controller)
    assert controller.export_system_snapshot() == before


def test_manual_recovery_does_not_overlay_durable_history(tmp_path: Path) -> None:
    config = config_for_data_dir(tmp_path / "data")
    build_app(config).prepare()
    manual = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=config.storage_root,
            sql_database_path=config.sql_database_path,
            install_starter_schema=False,
            automatic_recovery=False,
        )
    )
    status = manual.prepare()
    assert status.status == "empty"
    assert status.recovery == "manual_recovery_required"
    assert manual.controller.get_system_state().state_classification == "needs_replay"


def test_failed_starter_cutover_removes_staged_state_and_replays_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = config_for_data_dir(tmp_path / "data")
    composition = build_app(config)
    before = composition.controller.export_system_snapshot()

    def fail_cutover(_self: InProcessRtgController, _migration_id: str) -> object:
        raise RuntimeError("simulated cutover failure")

    monkeypatch.setattr(InProcessRtgController, "apply_migration_cutover", fail_cutover)
    with pytest.raises(VellisStartupFailed, match="installation failed"):
        composition.prepare()
    _assert_same_domain_state(composition.controller.export_system_snapshot(), before)

    monkeypatch.undo()
    restarted = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=config.storage_root,
            sql_database_path=config.sql_database_path,
            install_starter_schema=False,
            automatic_recovery=True,
        )
    )
    status = restarted.prepare()
    assert status.status == "empty"
    _assert_same_domain_state(restarted.controller.export_system_snapshot(), before)


def _controller(tmp_path: Path, schema: InMemoryRtgSchema) -> InProcessRtgController:
    return InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        schema,
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        SqliteStorage.open(tmp_path / "ledger.sqlite"),
    )


def _assert_same_domain_state(left: object, right: object) -> None:
    for feature in ("graph", "schema", "constraints", "migration"):
        assert getattr(left, feature) == getattr(right, feature)
