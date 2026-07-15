from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_codec import (
    decode_change_batch,
    decode_schema_definition,
    encode_json,
)
from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset
from apps.rtg_knowledge_graph.onboarding import config_for_data_dir
from apps.rtg_knowledge_graph.starter_schema import (
    VellisStartupFailed,
    install_everyday_life_ontology,
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
from components.runtime.message_runtime import RuntimeFailStopped, RuntimeHistoryQuery
from components.storage.json_file.implementation import LocalJsonFileStorage

MODEL_EVIDENCE = {
    "EverydayLifeOntologyVerification": (
        "test_everyday_life_bundle_is_exact_schema_only_and_deterministic",
        "test_modeled_ontology_installer_reports_installation_and_reuse",
        "test_everyday_life_ontology_install_is_idempotent_and_runtime_reconstructed",
        "test_custom_schema_is_preserved_and_not_overlaid",
        "test_snapshot_transfers_beta_shaped_custom_graph_with_overlapping_keys",
        "test_installed_ontology_can_be_extended_without_bootstrap_overwrite",
        "test_starter_identity_collision_fails_without_partial_effects",
        "test_partial_starter_installation_fails_without_partial_effects",
        "test_startup_completes_an_exact_interrupted_starter_staging",
        "test_empty_mode_abandons_an_exact_interrupted_starter_staging",
        "test_manual_recovery_does_not_overlay_durable_history",
        "test_manual_recovery_can_be_initiated_through_the_runtime_facade",
        "test_failed_starter_cutover_removes_staged_state_and_reconstructs_cleanly",
    ),
}


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
                key for key, rule in definition["payload"]["properties"].items() if rule["required"]
            ]
            assert required in (["name"], ["title"])


def test_modeled_ontology_installer_reports_installation_and_reuse(tmp_path: Path) -> None:
    controller = _controller(tmp_path, InMemoryRtgSchema.empty())

    installed = install_everyday_life_ontology(controller)
    reused = install_everyday_life_ontology(controller)

    assert installed.status == "installed"
    assert installed.schema_definition_count == 33
    assert installed.ontology.ontology_id == "ontology.vellis.everyday_life"
    assert installed.ontology.version == "1"
    assert installed.ontology.bootstrap_migration_id == "migration.vellis.everyday_life.v1"
    assert reused.status == "alreadyInstalled"
    assert reused.ontology == installed.ontology
    assert reused.schema_definition_count == 33


def test_everyday_life_ontology_install_is_idempotent_and_runtime_reconstructed(
    tmp_path: Path,
) -> None:
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
    first.close()

    with build_app(config) as restarted:
        reconstructed = restarted.prepare()
        assert reconstructed.status == "installed"
        assert reconstructed.recovery == "runtime_reconstructed"
        state = restarted.controller.get_system_state()
        assert state.live_schema_counts.total == 33
        assert state.state_classification == "populated"

        repeated = restarted.prepare()
        assert repeated.status == "installed"
        assert restarted.controller.get_system_state().live_schema_counts.total == 33


@pytest.mark.parametrize("type_key", ["CustomThing", "Person"])
def test_custom_schema_is_preserved_and_not_overlaid(tmp_path: Path, type_key: str) -> None:
    schema = InMemoryRtgSchema.empty()
    custom_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=custom_id,
            kind="anchor",
            type_key=type_key,
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
    assert snapshot.schema.definitions[0]["type_key"] == type_key

    installed = install_everyday_life_ontology(controller)
    assert installed.status == "customPreserved"
    assert installed.schema_definition_count == 0
    assert controller.export_system_snapshot() == snapshot


def test_snapshot_transfers_beta_shaped_custom_graph_with_overlapping_keys(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path / "source", InMemoryRtgSchema.empty())
    toolset = RtgMcpToolset(controller)
    anchor_types = ("Person", "Area", "Project", "Task", "Event", "Note", "Resource")
    definitions: list[dict[str, Any]] = []
    for type_key in anchor_types:
        facts_type = f"{type_key}Facts"
        definitions.extend(
            (
                {
                    "kind": "anchor",
                    "type_key": type_key,
                    "description": f"Custom beta {type_key}.",
                    "payload": {"required_data_types": [facts_type]},
                },
                {
                    "kind": "data_object",
                    "type_key": facts_type,
                    "description": f"Custom beta {type_key} facts.",
                    "payload": {
                        "properties": {"title": {"required": True, "value_kinds": ["string"]}}
                    },
                },
            )
        )
    definitions.append(
        {
            "kind": "link",
            "type_key": "belongs_to",
            "description": "Custom beta primary-area relation.",
            "payload": {
                "allowed_source_types": ["Project"],
                "allowed_target_types": ["Area"],
            },
        }
    )
    assert (
        toolset.rtg_stage_schema_migration(
            "custom-beta-bootstrap", "Install synthetic custom beta schema.", definitions
        )["ok"]
        is True
    )
    assert toolset.rtg_apply_migration_cutover("custom-beta-bootstrap")["ok"] is True
    records = [
        {
            "ref": {"local_ref": type_key.lower()},
            "type": type_key,
            "facts": [{"type": f"{type_key}Facts", "properties": {"title": type_key}}],
        }
        for type_key in anchor_types
    ]
    assert (
        toolset.rtg_apply_live_anchor_records(
            records,
            link_writes=[
                {
                    "ref": {"local_ref": "project-area"},
                    "type": "belongs_to",
                    "source_ref": {"local_ref": "project"},
                    "target_ref": {"local_ref": "area"},
                }
            ],
        )["ok"]
        is True
    )
    before = controller.export_system_snapshot()
    encoded = encode_json(before)
    assert isinstance(encoded, dict)
    transfer_snapshot = {
        **encoded,
        "transaction_id": "legacy-controller-trace",
        "ledger_position": 4321,
        "legacy_controller_metadata": {
            "ledger_schema": "controller-v1",
            "source_version": "pre-runtime",
        },
    }
    destination_config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "destination" / "json",
        runtime_database_path=tmp_path / "destination" / "runtime.sqlite",
        install_starter_schema=False,
        automatic_recovery=True,
    )

    with build_app(destination_config) as destination:
        initial = destination.prepare()
        assert initial.status == "empty"
        assert not destination.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect")
        ).facts

        facade = destination.build_facade(initial)
        restored = facade.rtg_restore_from_snapshot(transfer_snapshot)
        assert restored["ok"] is True
        assert restored["result"]["status"] == "restore_applied"

        after_restore = destination.controller.export_system_snapshot()
        _assert_same_domain_state(after_restore, before)
        effects = destination.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect")
        ).facts
        assert len(effects) == 5
        assert {(item.instance_key, item.action_id) for item in effects} == {
            ("vellis.graph.primary", "component.rtg.graph.replace_snapshot"),
            ("vellis.schema.primary", "component.rtg.schema.replace_snapshot"),
            ("vellis.constraints.primary", "component.rtg.constraints.replace_snapshot"),
            ("vellis.migration.primary", "component.rtg.migration.replace_snapshot"),
            (
                "vellis.controller.primary",
                "component.rtg.controller.restore_from_snapshot",
            ),
        }
        controller_effect = next(
            item for item in effects if item.instance_key == "vellis.controller.primary"
        )
        assert controller_effect.runtime_position == max(
            item.runtime_position for item in effects
        )
        effect = controller_effect.details["effect"]
        assert isinstance(effect, dict)
        payload = effect["payload"]
        assert isinstance(payload, dict)
        assert payload["supersedes_trace_effects"] is True
        arguments = payload["arguments"]
        assert isinstance(arguments, dict)
        canonical_snapshot = arguments["snapshot"]
        assert isinstance(canonical_snapshot, dict)
        assert "transaction_id" not in canonical_snapshot
        assert "ledger_position" not in canonical_snapshot
        assert "legacy_controller_metadata" not in canonical_snapshot
        destination_runtime_id = destination.runtime.runtime_id

    with build_app(destination_config) as restarted:
        status = restarted.prepare()
        after_restart = restarted.controller.export_system_snapshot()
        assert restarted.runtime.runtime_id == destination_runtime_id
        assert status.status == "custom"
        assert status.recovery == "runtime_reconstructed"
        _assert_same_domain_state(after_restart, before)
        assert len(after_restart.graph.anchors) == 7
        assert len(after_restart.graph.data_objects) == 7
        assert len(after_restart.graph.links) == 1
        assert len(after_restart.schema.definitions) == 15


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


def test_starter_identity_collision_fails_without_partial_effects(tmp_path: Path) -> None:
    bundle = load_starter_schema_bundle()
    first_definition = bundle["knowledge_changes"]["schema_changes"]["definition_writes"][0][
        "definition"
    ]
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=UUID(first_definition["uuid"]),
            kind="anchor",
            type_key="ConflictingPerson",
            description="Conflicts with a reserved starter identity.",
            payload=decode_schema_definition(first_definition).payload,
            system={"live": True},
        )
    )
    controller = _controller(tmp_path, schema)
    before = controller.export_system_snapshot()
    with pytest.raises(VellisStartupFailed, match="deterministic definition UUID"):
        prepare_controller(controller)
    assert controller.export_system_snapshot() == before


def test_partial_starter_installation_fails_without_partial_effects(tmp_path: Path) -> None:
    bundle = load_starter_schema_bundle()
    first_definition = bundle["knowledge_changes"]["schema_changes"]["definition_writes"][0][
        "definition"
    ]
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=UUID(first_definition["uuid"]),
            kind=first_definition["kind"],
            type_key=first_definition["type_key"],
            description=first_definition["description"],
            payload=decode_schema_definition(first_definition).payload,
            system={"live": True},
        )
    )
    controller = _controller(tmp_path, schema)
    before = controller.export_system_snapshot()
    with pytest.raises(VellisStartupFailed, match="partial Everyday Life"):
        prepare_controller(controller)
    assert controller.export_system_snapshot() == before


def test_startup_completes_an_exact_interrupted_starter_staging(tmp_path: Path) -> None:
    controller = _controller(tmp_path, InMemoryRtgSchema.empty())
    bundle = load_starter_schema_bundle()
    controller.stage_knowledge_changes(
        decode_change_batch(bundle["knowledge_changes"]), validation_mode="strict"
    )

    status = prepare_controller(controller)

    assert status.status == "installed"
    assert status.recovery == "starter_install_completed"
    assert controller.validate_graph().accepted is True


def test_empty_mode_abandons_an_exact_interrupted_starter_staging(tmp_path: Path) -> None:
    controller = _controller(tmp_path, InMemoryRtgSchema.empty())
    bundle = load_starter_schema_bundle()
    controller.stage_knowledge_changes(
        decode_change_batch(bundle["knowledge_changes"]), validation_mode="strict"
    )

    status = prepare_controller(controller, install_starter_schema=False)

    assert status.status == "empty"
    assert status.recovery == "starter_install_abandoned"
    assert controller.export_system_snapshot().schema.definitions == ()


def test_manual_recovery_does_not_overlay_durable_history(tmp_path: Path) -> None:
    config = config_for_data_dir(tmp_path / "data")
    with build_app(config) as initial:
        initial.prepare()
        assert initial.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect")
        ).facts
    with build_app(
        RtgKnowledgeGraphConfig(
            storage_root=config.storage_root,
            runtime_database_path=config.runtime_database_path,
            install_starter_schema=False,
            automatic_recovery=False,
        )
    ) as manual:
        status = manual.prepare()
        assert status.status == "empty"
        assert status.recovery == "manual_recovery_required"
        assert manual.runtime.health == "recovery_required"
        with pytest.raises(RuntimeFailStopped, match="recovery_required"):
            manual.controller.get_system_state()


def test_manual_recovery_can_be_initiated_through_the_runtime_facade(tmp_path: Path) -> None:
    config = config_for_data_dir(tmp_path / "data")
    with build_app(config) as initial:
        initial.prepare()
        source_snapshot = initial.controller.export_system_snapshot()

    with build_app(
        RtgKnowledgeGraphConfig(
            storage_root=config.storage_root,
            runtime_database_path=config.runtime_database_path,
            install_starter_schema=False,
            automatic_recovery=False,
        )
    ) as manual:
        status = manual.prepare()
        facade = manual.build_facade(status)
        with pytest.raises(RuntimeFailStopped, match="recovery_required"):
            manual.controller.restore_from_snapshot(source_snapshot)
        with pytest.raises(RuntimeFailStopped, match="recovery_required"):
            facade.rtg_get_usage_guide("schema_design")
        effects_before = manual.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect", limit=1000)
        ).facts
        messages_before = manual.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="message_accepted", limit=1000)
        ).facts

        replay = facade.rtg_replay_ledger()

        effects_after = manual.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect", limit=1000)
        ).facts
        messages_after = manual.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="message_accepted", limit=1000)
        ).facts
        assert replay["ok"] is True
        assert replay["result"]["verified"] is True
        assert replay["result"]["applied_effects"] > 0
        assert effects_after == effects_before
        assert len(messages_after) == len(messages_before) + 1
        assert manual.controller.export_system_snapshot() == source_snapshot
        assert facade.rtg_get_usage_guide("schema_design")["ok"] is True
        manual.controller.restore_from_snapshot(source_snapshot)


def test_failed_starter_cutover_removes_staged_state_and_reconstructs_cleanly(
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
    assert composition.runtime.health == "recovery_required"
    composition.close()

    monkeypatch.undo()
    with build_app(
        RtgKnowledgeGraphConfig(
            storage_root=config.storage_root,
            runtime_database_path=config.runtime_database_path,
            install_starter_schema=False,
            automatic_recovery=True,
        )
    ) as restarted:
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
    )


def _assert_same_domain_state(left: object, right: object) -> None:
    for feature in ("graph", "schema", "constraints", "migration"):
        assert getattr(left, feature) == getattr(right, feature)
