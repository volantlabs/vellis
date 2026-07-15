from __future__ import annotations

import asyncio
import json
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from apps.rtg_knowledge_graph.mcp_codec import (
    RtgMcpInputInvalid,
    decode_change_batch,
    decode_cutover_options,
    decode_discovery_options,
    decode_graph_changes,
    decode_migration_changes,
    decode_query_diagnostic_options,
    decode_query_options,
    decode_query_spec,
    decode_restore_options,
    decode_schema_changes,
    decode_schema_definition,
    decode_schema_field,
    decode_schema_pack_options,
    decode_validation_options,
    encode_json,
)
from apps.rtg_knowledge_graph.mcp_toolset import TOOL_NAMES, RtgMcpToolset, mcp_tool_metadata
from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    RtgChangeBatch,
    RtgChangeReference,
    RtgGraphChangeSet,
)
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import InProcessRtgController
from components.rtg.diagnostics import diagnostic_as_json
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.migration import InMemoryRtgMigration
from components.rtg.query import SimpleRtgQueryEngine
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaField,
)
from components.storage.json_file import LocalJsonFileStorage
from components.storage.sql import SqliteStorage


def build_schema() -> InMemoryRtgSchema:
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="Person.",
            payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
            time_shape="state_now",
        )
    )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="Profile.",
            payload=RtgDataObjectSchemaPayload(
                properties={"name": RtgSchemaField(required=True, value_kinds=("string",))}
            ),
            time_shape="state_now",
        )
    )
    return schema


def build_toolset(tmp_path: Path) -> RtgMcpToolset:
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        SqliteStorage.open(tmp_path / "controller.sqlite"),
    )
    return RtgMcpToolset(controller)


def build_empty_toolset(tmp_path: Path) -> RtgMcpToolset:
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        InMemoryRtgSchema.empty(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        SqliteStorage.open(tmp_path / "controller.sqlite"),
    )
    return RtgMcpToolset(controller)


MODEL_EVIDENCE = {
    "VellisMcpOutcomeContractVerification": (
        "test_mcp_codec_decodes_changes_and_encodes_json",
        "test_mcp_toolset_live_graph_query_get_object_and_validation_error",
        "test_mcp_toolset_keeps_error_shape_for_unexpected_exceptions",
        "test_mcp_toolset_errors_include_ref_and_uuid_diagnostics",
    ),
    "VellisMcpBoundaryVerification": (
        "test_mcp_codec_decodes_changes_and_encodes_json",
        "test_mcp_codec_rejects_malformed_boolean_options",
        "test_mcp_codec_reports_path_specific_reference_and_uuid_errors",
        "test_mcp_codec_rejects_query_aliases_that_would_be_ignored",
        "test_mcp_codec_rejects_malformed_query_return_properties",
        "test_mcp_codec_rejects_non_string_query_terms",
        "test_mcp_codec_rejects_non_string_option_terms",
        "test_mcp_codec_rejects_mutation_aliases_that_would_be_ignored",
        "test_mcp_toolset_rejects_wrong_mutation_fields_instead_of_noop",
        "test_mcp_codec_accepts_schema_field_null_items_from_json_round_trip",
        "test_rtg_mcp_skill_item_schema_live_write_and_query_path_runs",
        "test_mcp_toolset_live_graph_query_get_object_and_validation_error",
        "test_mcp_toolset_validates_live_graph_changes_without_mutation_or_ledger",
        "test_mcp_toolset_validates_and_applies_live_anchor_records",
        "test_compact_mutation_response_is_materially_smaller_than_full",
        "test_properties_only_preserves_aggregation_rows_and_pagination_metadata",
        "test_invalid_mutation_response_format_fails_before_controller_invocation",
        "test_mcp_properties_only_without_returned_properties_teaches_return_spec",
        "test_mcp_toolset_resolves_anchor_by_fact_through_query_facade",
        "test_mcp_toolset_resolve_anchor_by_fact_reports_ambiguous_matches",
        "test_mcp_toolset_stages_cuts_over_and_reads_schema_migration",
        "test_mcp_toolset_snapshot_ledger_restore_tools",
        "test_mcp_toolset_system_state_guides_schema_staging_and_abandonment",
        "test_schema_migration_rejects_duplicate_definition_correlation_keys_before_mutation",
        "test_mcp_toolset_system_state_workflows_for_schema_and_populated_states",
        "test_mcp_usage_guides_are_packaged_and_do_not_return_fake_snapshot_payloads",
        "test_mcp_generic_usage_guides_do_not_leak_beta_domain_terms",
        "test_mcp_exposes_modeled_everyday_life_and_schema_design_guidance",
        "test_mcp_toolset_stage_schema_migration_can_replace_live_schema",
        "test_mcp_toolset_persisted_snapshot_readback",
        "test_mcp_toolset_replay_path_and_migration_history",
        "test_mcp_toolset_keeps_error_shape_for_unexpected_exceptions",
        "test_mcp_toolset_rejects_unsupported_controller_options",
        "test_mcp_toolset_errors_include_ref_and_uuid_diagnostics",
        "test_diagnostic_json_normalization_preserves_nested_sequences",
        "test_mcp_tool_metadata_is_concise_complete_and_annotated",
        "test_mcp_server_stdio_protocol_lists_tools_from_non_repo_cwd",
        "test_mcp_server_http_protocol_lists_tools_from_non_repo_cwd",
    ),
}


def test_mcp_codec_decodes_changes_and_encodes_json() -> None:
    payload = {
        "anchor_writes": [
            {"ref": {"local_ref": "person"}, "type": "Person", "display_name": "Ada"}
        ],
        "data_object_writes": [
            {
                "ref": {"local_ref": "profile"},
                "type": "Profile",
                "mode": "merge",
                "properties": {"name": "Ada"},
                "anchor_refs": [{"local_ref": "person"}],
            }
        ],
    }

    graph_changes = decode_graph_changes(payload)
    batch = decode_change_batch({"graph_changes": payload})

    assert isinstance(graph_changes, RtgGraphChangeSet)
    assert isinstance(batch, RtgChangeBatch)
    assert graph_changes.anchor_writes[0].ref == RtgChangeReference(local_ref="person")
    assert encode_json({"uuid": UUID("11111111-1111-1111-1111-111111111111")}) == {
        "uuid": "11111111-1111-1111-1111-111111111111"
    }


def test_mcp_codec_rejects_malformed_boolean_options() -> None:
    valid = decode_query_spec(
        {
            "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
            "data_requirements": [
                {
                    "name": "profile",
                    "anchor_bucket": "person",
                    "data_type_key": "Profile",
                    "required": False,
                }
            ],
        }
    )

    assert valid.data_requirements[0].required is False
    assert valid.return_spec.properties == ()
    assert valid.diagnostic_options.include_non_fatal is True
    assert valid.diagnostic_options.unknown_term_guidance == "suggest_discovery"

    with_property = decode_query_spec(
        {
            "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
            "data_requirements": [
                {
                    "name": "profile",
                    "anchor_bucket": "person",
                    "data_type_key": "Profile",
                }
            ],
            "return_spec": {"properties": [["profile", ["name"]]]},
        }
    )
    assert with_property.return_spec.properties == (("profile", ("name",)),)

    malformed_payloads = (
        lambda: decode_query_spec(
            {
                "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
                "data_requirements": [
                    {
                        "name": "profile",
                        "anchor_bucket": "person",
                        "data_type_key": "Profile",
                        "required": "false",
                    }
                ],
            }
        ),
        lambda: decode_cutover_options({"prune_retired": "false"}),
        lambda: decode_discovery_options({"include_non_live": 1}),
        lambda: decode_schema_pack_options({"include_live_counts": "true"}),
    )

    for decode in malformed_payloads:
        try:
            decode()
        except RtgMcpInputInvalid:
            pass
        else:
            raise AssertionError("malformed boolean payload should be rejected")


def test_mcp_codec_reports_path_specific_reference_and_uuid_errors() -> None:
    with pytest.raises(RtgMcpInputInvalid) as ref_error:
        decode_schema_changes(
            {
                "definition_writes": [
                    {
                        "ref": "schema-1",
                        "definition": {
                            "kind": "anchor",
                            "type_key": "Task",
                            "description": "Task.",
                            "payload": {},
                        },
                    }
                ]
            }
        )
    with pytest.raises(RtgMcpInputInvalid) as uuid_error:
        decode_migration_changes(
            {
                "migration_writes": [
                    {
                        "ref": {"resource_id": "bad"},
                        "migration": {
                            "migration_id": "bad",
                            "description": "Bad migration.",
                            "schema_make_live": ["Task"],
                        },
                    }
                ]
            }
        )

    assert "definition_writes.ref must be an object" in str(ref_error.value)
    assert "migration_record.schema_make_live[0] must be a UUID" in str(uuid_error.value)


def test_mcp_codec_decodes_reviewed_schema_evolution_ops() -> None:
    old_definition = uuid4()
    new_definition = uuid4()
    changes = decode_migration_changes(
        {
            "migration_writes": [
                {
                    "ref": {"resource_id": "profile-rename"},
                    "migration": {
                        "migration_id": "profile-rename",
                        "description": "Rename Profile.name.",
                        "schema_make_live": [str(new_definition)],
                        "schema_make_non_live": [str(old_definition)],
                        "schema_evolution_ops": [
                            {
                                "op_id": "rename-profile-name",
                                "op_kind": "rename_property",
                                "target_kind": "data_object",
                                "target_type_key": "Profile",
                                "property_key": "name",
                                "replacement_key": "full_name",
                                "source_definition_uuid": str(old_definition),
                                "candidate_definition_uuid": str(new_definition),
                                "data_implication": "rename_existing_values",
                            }
                        ],
                    },
                }
            ]
        }
    )

    op = changes.migration_writes[0].migration.schema_evolution_ops[0]

    assert op.op_id == "rename-profile-name"
    assert op.source_definition_uuid == old_definition
    assert op.candidate_definition_uuid == new_definition


def test_mcp_codec_rejects_query_aliases_that_would_be_ignored() -> None:
    malformed_payloads = (
        (
            {
                "anchor_buckets": [{"name": "person", "types": ["Person"]}],
            },
            "types",
            "anchor_type_keys",
        ),
        (
            {
                "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
                "data_requirements": [
                    {
                        "name": "profile",
                        "anchor_bucket": "person",
                        "data_type_key": "Profile",
                        "property_predicates": [
                            {"path": ["name"], "operator": "equals", "value": "Ada"}
                        ],
                    }
                ],
            },
            "property_predicates",
            "predicates",
        ),
        (
            {
                "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
                "return_spec": {"fields": [["profile", ["name"]]]},
            },
            "fields",
            "properties",
        ),
    )

    for payload, wrong_key, suggested_key in malformed_payloads:
        with pytest.raises(RtgMcpInputInvalid) as error:
            decode_query_spec(payload)
        assert wrong_key in str(error.value)
        assert suggested_key in str(error.value)


def test_mcp_codec_rejects_malformed_query_return_properties() -> None:
    with pytest.raises(RtgMcpInputInvalid) as error:
        decode_query_spec(
            {
                "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
                "return_spec": {"properties": [["profile"]]},
            }
        )

    assert "query_return_spec.properties[0]" in str(error.value)


def test_mcp_codec_rejects_non_string_query_terms() -> None:
    malformed_payloads = (
        (
            {
                "anchor_buckets": [{"name": "person", "anchor_type_keys": [123]}],
            },
            "query_spec.anchor_buckets[0].anchor_type_keys",
        ),
        (
            {
                "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
                "return_spec": {"properties": [[123, ["name"]]]},
            },
            "query_return_spec.properties[0][0]",
        ),
        (
            {
                "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
                "return_spec": {"properties": [["profile", [1]]]},
            },
            "query_return_spec.properties[0][1]",
        ),
    )

    for payload, label in malformed_payloads:
        with pytest.raises(RtgMcpInputInvalid) as error:
            decode_query_spec(payload)
        assert label in str(error.value)


def test_mcp_codec_rejects_non_string_option_terms() -> None:
    malformed_payloads = (
        lambda: decode_query_options({"live_filter": 1}),
        lambda: decode_query_diagnostic_options({"unknown_term_guidance": 1}),
        lambda: decode_query_diagnostic_options({"unknown_term_guidance": "invent_schema"}),
        lambda: decode_cutover_options({"validation_mode": 1}),
        lambda: decode_cutover_options({"failure_restore": 1}),
        lambda: decode_validation_options({"tracks": [1]}),
        lambda: decode_restore_options({"ledger_mode": 1}),
        lambda: decode_migration_changes(
            {
                "status_changes": [
                    {
                        "migration_ref": {"resource_id": 123},
                        "status": "ready",
                    }
                ]
            }
        ),
    )

    for decode in malformed_payloads:
        with pytest.raises(RtgMcpInputInvalid):
            decode()


def test_validation_option_codec_maps_transport_shorthand_to_modeled_shape() -> None:
    all_tracks = decode_validation_options({"tracks": "all", "finding_limit": 20})
    selected_tracks = decode_validation_options({"tracks": ["schema_object"]})

    assert all_tracks is not None
    assert all_tracks.selection == "all"
    assert all_tracks.tracks == ()
    assert all_tracks.finding_limit == 20
    assert selected_tracks is not None
    assert selected_tracks.selection == "selected"
    assert selected_tracks.tracks == ("schema_object",)


def test_mcp_codec_rejects_mutation_aliases_that_would_be_ignored() -> None:
    malformed_payloads = (
        (lambda: decode_graph_changes({"anchors": []}), "anchors", "anchor_writes"),
        (lambda: decode_graph_changes({"data_objects": []}), "data_objects", "data_object_writes"),
        (
            lambda: decode_change_batch({"schema": {"definition_writes": []}}),
            "schema",
            "schema_changes",
        ),
        (lambda: decode_schema_changes({"definitions": []}), "definitions", "definition_writes"),
        (lambda: decode_migration_changes({"migrations": []}), "migrations", "migration_writes"),
        (
            lambda: decode_graph_changes(
                {"anchor_writes": [{"ref": {"local_ref": "task"}, "type_key": "Task"}]}
            ),
            "type_key",
            "type",
        ),
    )

    for decode, wrong_key, suggested_key in malformed_payloads:
        with pytest.raises(RtgMcpInputInvalid) as error:
            decode()
        assert wrong_key in str(error.value)
        assert suggested_key in str(error.value)


def test_mcp_toolset_rejects_wrong_mutation_fields_instead_of_noop(
    tmp_path: Path,
) -> None:
    toolset = build_empty_toolset(tmp_path)

    response = toolset.rtg_apply_live_graph_changes({"anchors": []})

    assert response["ok"] is False
    assert response["error"]["type"] == "RtgMcpInputInvalid"
    assert "anchor_writes" in response["error"]["message"]


def test_mcp_codec_accepts_schema_field_null_items_from_json_round_trip() -> None:
    field = decode_schema_field(
        {
            "required": True,
            "value_kinds": ["string"],
            "properties": {},
            "items": None,
        }
    )

    assert field.required is True
    assert field.value_kinds == ("string",)
    assert field.items is None


def test_rtg_mcp_skill_item_schema_live_write_and_query_path_runs(
    tmp_path: Path,
) -> None:
    toolset = build_empty_toolset(tmp_path)
    skill_text = Path(".agents/skills/rtg-knowledge-graph-mcp/SKILL.md").read_text(encoding="utf-8")
    schema_call = _skill_json_block_after(skill_text, "Stage schema definitions")
    live_write_call = _skill_json_block_after(skill_text, "minimal live write should succeed")
    cutover_call = _skill_json_block_after(skill_text, "Then call:")
    query_call = _skill_json_block_after(skill_text, "Use exact key names")

    staged = toolset.rtg_stage_knowledge_changes(
        cast(dict[str, Any], schema_call["knowledge_changes"]),
        validation_mode=str(schema_call["validation_mode"]),
    )
    cutover = toolset.rtg_apply_migration_cutover(str(cutover_call["migration_id"]))
    applied = toolset.rtg_apply_live_graph_changes(
        cast(dict[str, Any], live_write_call["graph_changes"]),
        validation_mode=str(live_write_call["validation_mode"]),
    )
    query = toolset.rtg_execute_query(
        cast(dict[str, Any], query_call["query_spec"]),
        cast(dict[str, Any], query_call["query_options"]),
    )

    assert staged["ok"] is True
    assert cutover["ok"] is True
    assert applied["ok"] is True
    assert query["ok"] is True
    assert query["result"]["returns"][0]["properties"]["facts"] == {
        "title": "Item alpha",
        "priority": 1,
    }


def test_mcp_toolset_live_graph_query_get_object_and_validation_error(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)

    malformed = toolset.rtg_apply_live_graph_changes({"anchor_writes": [{"type": "Person"}]})
    invalid = toolset.rtg_apply_live_graph_changes(
        {
            "anchor_writes": [
                {"ref": {"local_ref": "person"}, "type": "Person"},
            ]
        }
    )

    assert invalid["ok"] is False
    assert invalid["error"]["type"] == "RtgControllerValidationFailed"
    assert invalid["validation_report"]["findings"]

    applied = toolset.rtg_apply_live_graph_changes(
        {
            "anchor_writes": [
                {"ref": {"local_ref": "person"}, "type": "Person"},
            ],
            "data_object_writes": [
                {
                    "ref": {"local_ref": "profile"},
                    "type": "Profile",
                    "mode": "merge",
                    "properties": {"name": "Ada"},
                    "anchor_refs": [{"local_ref": "person"}],
                }
            ],
        }
    )
    query = toolset.rtg_execute_query(
        {"anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}]}
    )
    object_uuid = query["result"]["bindings"][0]["anchors"]["person"]
    read = toolset.rtg_get_object(object_uuid)
    missing = toolset.rtg_get_object("11111111-1111-1111-1111-111111111111")

    assert malformed["ok"] is False
    assert malformed["error"]["type"] == "RtgMcpInputInvalid"
    assert applied["ok"] is True
    assert query["ok"] is True
    assert read["result"]["object"]["type"] == "Person"
    assert read["result"]["version_token"] is None
    assert missing["ok"] is False
    assert missing["error"]["type"] == "RtgControllerObjectNotFound"


def test_mcp_toolset_validates_live_graph_changes_without_mutation_or_ledger(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)

    preview = toolset.rtg_validate_live_graph_changes(
        {
            "anchor_writes": [{"ref": {"local_ref": "person"}, "type": "Person"}],
            "data_object_writes": [
                {
                    "ref": {"local_ref": "profile"},
                    "type": "Profile",
                    "mode": "merge",
                    "properties": {"name": "Ada"},
                    "anchor_refs": [{"local_ref": "person"}],
                }
            ],
        }
    )
    state_after_preview = toolset.rtg_get_system_state()
    query_after_preview = toolset.rtg_execute_query(
        {"anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}]}
    )

    assert preview["ok"] is True
    assert preview["result"]["status"] == "validated"
    assert preview["result"]["mutation_state"] == "not_mutated"
    assert preview["result"]["accepted"] is True
    assert set(preview["result"]["generated_ids"]) == {"person", "profile"}
    assert (
        preview["result"]["resolved_graph_changes"]["anchor_writes"][0]["ref"]["resource_id"]
        == preview["result"]["generated_ids"]["person"]
    )
    assert state_after_preview["result"]["ledger_record_count"] == 0
    assert query_after_preview["result"]["bindings"] == []


def test_mcp_replace_uses_read_token_and_returns_stale_conflict_state(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)
    person_uuid = str(uuid4())
    profile_uuid = str(uuid4())
    created = toolset.rtg_apply_live_graph_changes(
        {
            "anchor_writes": [
                {
                    "ref": {"resource_id": person_uuid},
                    "type": "Person",
                    "display_name": "Ada",
                }
            ],
            "data_object_writes": [
                {
                    "ref": {"resource_id": profile_uuid},
                    "type": "Profile",
                    "mode": "merge",
                    "properties": {"name": "Ada"},
                    "anchor_refs": [{"resource_id": person_uuid}],
                }
            ],
        }
    )
    read = toolset.rtg_get_object(profile_uuid)
    version_token = read["result"]["version_token"]
    replacement = {
        "data_object_writes": [
            {
                "ref": {"resource_id": profile_uuid},
                "type": "Profile",
                "mode": "replace",
                "expected_version": version_token,
                "properties": {"name": "Grace"},
                "anchor_refs": [{"resource_id": person_uuid}],
            }
        ]
    }

    applied = toolset.rtg_apply_live_graph_changes(replacement)
    stale = toolset.rtg_apply_live_graph_changes(replacement)

    assert created["ok"] is True
    assert applied["ok"] is True
    assert stale["ok"] is False
    assert stale["error"]["type"] == "RtgControllerWriteConflict"
    assert stale["transaction_id"]
    assert stale["conflicts"][0]["current_object"]["properties"] == {"name": "Grace"}
    assert stale["conflicts"][0]["current_version"] != version_token


def test_mcp_toolset_validates_and_applies_live_anchor_records(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)

    preview = toolset.rtg_validate_live_anchor_records(
        [
            {
                "ref": {"local_ref": "ada"},
                "type": "Person",
                "display_name": "Ada",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            }
        ]
    )
    query_after_preview = toolset.rtg_execute_query(
        {"anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}]}
    )
    applied = toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "ada"},
                "type": "Person",
                "display_name": "Ada",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            }
        ]
    )
    compact_query = toolset.rtg_execute_query(
        {
            "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
            "data_requirements": [
                {
                    "name": "profile",
                    "anchor_bucket": "person",
                    "data_type_key": "Profile",
                }
            ],
            "return_spec": {
                "anchor_buckets": ["person"],
                "data_requirements": ["profile"],
                "properties": [["profile", ["name"]]],
            },
        },
        response_options={"format": "properties_only"},
    )
    full_query = toolset.rtg_execute_query(
        {
            "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
        }
    )

    assert preview["ok"] is True
    assert preview["result"]["validation"]["mutation_state"] == "not_mutated"
    assert preview["result"]["validation"]["accepted"] is True
    assert preview["result"]["generated_refs"]["facts"][0]["local_ref"] == "ada-fact-1"
    assert preview["result"]["submitted_graph_changes"]["data_object_writes"][0]["anchor_refs"] == [
        {"local_ref": "ada"}
    ]
    assert query_after_preview["result"]["bindings"] == []
    assert applied["ok"] is True
    assert applied["result"]["format"] == "compact"
    assert "submitted_graph_changes" not in applied["result"]
    assert set(applied["result"]["generated_ids"]) == {"ada", "ada-fact-1"}
    assert applied["result"]["generated_ids"] == applied["result"]["operation"]["generated_ids"]
    assert applied["result"]["operation"]["status"] == "applied"
    assert compact_query["result"]["format"] == "properties_only"
    assert compact_query["result"]["kind"] == "properties_only"
    assert compact_query["result"]["row_count"] == 1
    assert compact_query["result"]["rows"][0]["properties"]["profile"]["name"] == "Ada"
    assert "bindings" not in compact_query["result"]
    assert "next_offset" not in compact_query["result"]
    assert full_query["result"]["kind"] == "full"
    assert "next_offset" not in full_query["result"]


def test_compact_mutation_response_is_materially_smaller_than_full(tmp_path: Path) -> None:
    records = [
        {
            "ref": {"local_ref": f"person-{index}"},
            "type": "Person",
            "display_name": f"Person {index}",
            "facts": [
                {
                    "type": "Profile",
                    "mode": "merge",
                    "properties": {"name": f"Person {index} " + "planning context " * 15},
                }
            ],
        }
        for index in range(29)
    ]
    compact = build_toolset(tmp_path / "compact").rtg_apply_live_anchor_records(records)
    full = build_toolset(tmp_path / "full").rtg_apply_live_anchor_records(
        records, response_options={"format": "full"}
    )
    compact_bytes = len(json.dumps(compact, separators=(",", ":")))
    full_bytes = len(json.dumps(full, separators=(",", ":")))
    assert compact["result"]["format"] == "compact"
    assert full["result"]["format"] == "full"
    assert "submitted_graph_changes" in full["result"]
    assert compact_bytes <= full_bytes * 0.4
    assert compact["result"]["generated_ids"].keys() == full["result"]["generated_ids"].keys()


def test_properties_only_preserves_aggregation_rows_and_pagination_metadata(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)
    toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": f"ada-{index}"},
                "type": "Person",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            }
            for index in range(2)
        ]
    )

    compact = toolset.rtg_execute_query(
        {
            "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
            "data_requirements": [
                {
                    "name": "profile",
                    "anchor_bucket": "person",
                    "data_type_key": "Profile",
                }
            ],
            "return_spec": {
                "properties": [["profile", ["name"]]],
                "group_by": [["profile", ["name"]]],
                "aggregations": [
                    {"name": "person_count", "function": "count", "binding": "person"}
                ],
            },
        },
        response_options={"format": "properties_only"},
    )

    result = compact["result"]
    assert result["kind"] == "properties_only"
    assert result["rows"] == [
        {
            "row_index": 0,
            "group_by": {"profile": {"name": "Ada"}},
            "person_count": 2,
        }
    ]
    assert result["row_count"] == 1
    assert result["total_row_count"] == 1
    assert result["returned_row_count"] == 1
    assert "next_offset" not in result


def test_invalid_mutation_response_format_fails_before_controller_invocation(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)
    rejected = toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "ada"},
                "type": "Person",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            }
        ],
        response_options={"format": "verbose"},
    )
    state = toolset.rtg_get_system_state()["result"]
    assert rejected["ok"] is False
    assert rejected["error"]["diagnostic"]["path"] == "response_options.format"
    assert state["ledger_record_count"] == 0
    assert state["live_object_counts"]["counts"] == []


def test_mcp_properties_only_without_returned_properties_teaches_return_spec(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)
    toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "ada"},
                "type": "Person",
                "display_name": "Ada",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            }
        ]
    )

    compact_query = toolset.rtg_execute_query(
        {
            "anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}],
            "data_requirements": [
                {
                    "name": "profile",
                    "anchor_bucket": "person",
                    "data_type_key": "Profile",
                }
            ],
            "return_spec": {"anchor_buckets": ["person"], "data_requirements": ["profile"]},
        },
        response_options={"format": "properties_only"},
    )

    assert compact_query["ok"] is True
    diagnostic = compact_query["result"]["diagnostics"][0]["diagnostic"]
    assert diagnostic["code"] == "query.return_properties_empty"
    assert diagnostic["path"] == "query_spec.return_spec.properties"
    assert diagnostic["guide_topics"] == [
        "workflow_patterns",
        "query_examples",
        "tool_call_shapes",
    ]


def test_mcp_toolset_resolves_anchor_by_fact_through_query_facade(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)
    toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "ada"},
                "type": "Person",
                "display_name": "Ada",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            },
            {
                "ref": {"local_ref": "grace"},
                "type": "Person",
                "display_name": "Grace",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Grace"}}],
            },
        ]
    )

    resolved = toolset.rtg_resolve_anchor_by_fact(
        "Person",
        "Profile",
        ["name"],
        "Ada",
    )
    missing = toolset.rtg_resolve_anchor_by_fact(
        "Person",
        "Profile",
        ["name"],
        "Katherine",
    )

    assert resolved["ok"] is True
    assert resolved["result"]["match_count"] == 1
    assert resolved["result"]["matches"][0]["properties"]["facts"]["name"] == "Ada"
    assert resolved["result"]["submitted_query"]["query_spec"]["anchor_buckets"][0] == {
        "name": "anchor",
        "anchor_type_keys": ["Person"],
    }
    assert "matches[0].resource_id" in resolved["result"]["guidance"]
    assert missing["result"]["match_count"] == 0
    assert "No live anchor matched" in missing["result"]["guidance"]


def test_mcp_toolset_resolve_anchor_by_fact_reports_ambiguous_matches(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)
    toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "ada-1"},
                "type": "Person",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            },
            {
                "ref": {"local_ref": "ada-2"},
                "type": "Person",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            },
        ]
    )

    resolved = toolset.rtg_resolve_anchor_by_fact(
        "Person",
        "Profile",
        ["name"],
        "Ada",
    )
    malformed = toolset.rtg_resolve_anchor_by_fact(
        "Person",
        "Profile",
        [],
        "Ada",
    )

    assert resolved["ok"] is True
    assert resolved["result"]["match_count"] == 2
    assert "Multiple live anchors matched" in resolved["result"]["guidance"]
    assert malformed["ok"] is False
    assert "property_path must contain at least one property name" in malformed["error"]["message"]


def test_mcp_toolset_stages_cuts_over_and_reads_schema_migration(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)
    old_schema = toolset.rtg_get_schema_pack(["Person"])["result"]["schema_pack"]["anchor_schemas"][
        0
    ]
    assert decode_schema_definition(old_schema).type_key == "Person"
    profile_schema = toolset.rtg_get_schema_pack(["Person"])["result"]["schema_pack"][
        "associated_data_object_schemas"
    ][0]
    assert "allowed_values" not in profile_schema["payload"]["properties"]["name"]
    assert decode_schema_definition(profile_schema).type_key == "Profile"
    replacement_uuid = str(uuid4())
    migration_uuid = str(uuid4())
    knowledge_changes = {
        "schema_changes": {
            "definition_writes": [
                {
                    "ref": {"resource_id": replacement_uuid},
                    "definition": {
                        "uuid": replacement_uuid,
                        "kind": "anchor",
                        "type_key": "Person",
                        "description": "Expanded person.",
                        "payload": {"required_data_types": ["Profile"]},
                        "time_shape": "state_now",
                        "system": {"live": False},
                    },
                }
            ]
        },
        "migration_changes": {
            "migration_writes": [
                {
                    "ref": {"resource_id": migration_uuid},
                    "migration": {
                        "migration_id": migration_uuid,
                        "description": "Replace Person schema.",
                        "status": "ready",
                        "schema_make_live": [replacement_uuid],
                        "schema_make_non_live": [old_schema["uuid"]],
                    },
                }
            ]
        },
    }

    unscoped = toolset.rtg_stage_knowledge_changes(
        {"schema_changes": knowledge_changes["schema_changes"]}
    )
    staged = toolset.rtg_stage_knowledge_changes(knowledge_changes)
    migration = toolset.rtg_get_migration(migration_uuid)
    migrations = toolset.rtg_list_migrations()
    cutover = toolset.rtg_apply_migration_cutover(migration_uuid)
    discovery = toolset.rtg_discover_anchor_types()
    missing = toolset.rtg_get_migration("missing-migration")

    assert unscoped["ok"] is False
    assert staged["ok"] is True
    assert migration["result"]["migration_id"] == migration_uuid
    assert len(migrations["result"]["migrations"]) == 1
    assert cutover["ok"] is True
    assert discovery["result"]["anchor_types"][0]["description"] == "Expanded person."
    assert missing["ok"] is False
    assert missing["error"]["type"] == "RtgMigrationNotFound"


def test_mcp_toolset_snapshot_ledger_restore_tools(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)

    snapshot = toolset.rtg_export_system_snapshot()
    compact_snapshot = toolset.rtg_export_system_snapshot(summary=True)
    persisted = toolset.rtg_persist_system_snapshot("system/snapshot.json", return_snapshot=False)
    validation = toolset.rtg_validate_graph()
    replay = toolset.rtg_replay_ledger()
    replay_verification = toolset.rtg_verify_replay_from_ledger(
        {"start_snapshot_path": "system/snapshot.json"}
    )
    flush = toolset.rtg_flush_ledger_failures()
    restored = toolset.rtg_restore_from_snapshot(snapshot["result"])

    assert snapshot["ok"] is True
    assert snapshot["result"]["kind"] == "full"
    assert compact_snapshot["result"]["kind"] == "summary"
    assert compact_snapshot["result"]["status"] == "snapshot_exported"
    assert "snapshot" not in compact_snapshot["result"]
    assert persisted["result"]["status"] == "snapshot_persisted"
    assert "snapshot" not in persisted["result"]
    assert persisted["result"]["summary"]["schema_type_counts"]["anchor"] >= 1
    assert validation["result"]["accepted"] is True
    assert replay["ok"] is False
    assert replay_verification["result"]["status"] == "replay_verified"
    assert replay_verification["result"]["replay_window"]["start_source"] == "start_snapshot_path"
    assert flush["result"]["status"] == "ledger_failures_flushed"
    assert restored["result"]["status"] == "restore_applied"
    assert "rtg_apply_live_graph_changes" in TOOL_NAMES
    assert "rtg_get_agent_affordance_eval_prompt" not in TOOL_NAMES


def test_mcp_toolset_system_state_guides_schema_staging_and_abandonment(
    tmp_path: Path,
) -> None:
    toolset = build_empty_toolset(tmp_path)

    initial_state = toolset.rtg_get_system_state()
    guide = toolset.rtg_get_usage_guide("schema_staging_minimal")
    staged = toolset.rtg_stage_schema_migration(
        migration_id="minimal-item-schema",
        description="Introduce minimal item schema.",
        schema_definitions=cast(
            list[dict[str, Any]],
            guide["result"]["arguments"]["schema_definitions"],
        ),
    )
    staged_state = toolset.rtg_get_system_state()
    abandoned = toolset.rtg_abandon_migration(
        "minimal-item-schema",
        reason="Exercise staged cleanup.",
    )
    final_state = toolset.rtg_get_system_state()

    assert initial_state["result"]["state_classification"] == "empty"
    assert initial_state["result"]["recommended_workflows"] == [
        "connection_state_check",
        "schema_bootstrap",
    ]
    assert guide["result"]["tool"] == "rtg_stage_schema_migration"
    assert staged["ok"] is True
    assert staged["result"]["operation"]["status"] == "applied"
    assert (
        staged["result"]["operation"]["details"]["operation_effect"] == "staged_candidates_written"
    )
    assert set(staged["result"]["generated_schema_ids"]) == {
        "data_object:ItemFacts",
        "anchor:Item",
        "data_object:CollectionFacts",
        "anchor:Collection",
        "link:contains",
        "link:related_to",
    }
    assert staged_state["result"]["state_classification"] == "has_staged_work"
    assert staged_state["result"]["recommended_workflows"] == [
        "staged_work_review",
        "cutover_or_abandon",
    ]
    assert abandoned["result"]["status"] == "migration_abandoned"
    assert abandoned["result"]["details"]["pruned_candidates"]["schema"]
    assert final_state["result"]["state_classification"] == "needs_replay"
    assert final_state["result"]["recommended_workflows"] == ["replay_recovery"]
    assert "empty state is intentional" in " ".join(final_state["result"]["recommended_next_steps"])


def test_schema_migration_rejects_duplicate_definition_correlation_keys_before_mutation(
    tmp_path: Path,
) -> None:
    toolset = build_empty_toolset(tmp_path)
    duplicate = {
        "kind": "anchor",
        "type_key": "Item",
        "description": "An item.",
        "payload": {"required_data_types": []},
    }

    rejected = toolset.rtg_stage_schema_migration(
        migration_id="duplicate-item-schema",
        description="Must not create an ambiguous generated-ID mapping.",
        schema_definitions=[duplicate, duplicate],
    )
    state = toolset.rtg_get_system_state()["result"]

    assert rejected["ok"] is False
    assert rejected["error"]["type"] == "RtgMcpInputInvalid"
    assert "unique kind and type_key pairs" in rejected["error"]["message"]
    assert state["ledger_record_count"] == 0
    assert state["live_schema_counts"]["total"] == 0
    assert state["migration_counts_by_status"]["total"] == 0


def test_mcp_toolset_system_state_workflows_for_schema_and_populated_states(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)

    schema_only = toolset.rtg_get_system_state()
    applied = toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "ada"},
                "type": "Person",
                "display_name": "Ada",
                "facts": [{"type": "Profile", "mode": "merge", "properties": {"name": "Ada"}}],
            }
        ]
    )
    populated = toolset.rtg_get_system_state()

    assert schema_only["result"]["state_classification"] == "schema_only"
    assert schema_only["result"]["recommended_workflows"] == [
        "schema_discovery",
        "data_ingest",
    ]
    assert applied["ok"] is True
    assert populated["result"]["state_classification"] == "populated"
    assert populated["result"]["recommended_workflows"] == [
        "query_answer",
        "safe_update",
        "snapshot_replay_check",
    ]


def test_mcp_usage_guides_are_packaged_and_do_not_return_fake_snapshot_payloads(
    tmp_path: Path,
) -> None:
    toolset = build_empty_toolset(tmp_path)

    checklist = toolset.rtg_get_usage_guide("mcp_bootstrap_checklist")
    workflows = toolset.rtg_get_usage_guide("workflow_patterns")
    requests = toolset.rtg_get_usage_guide("request_patterns")
    recovery = toolset.rtg_get_usage_guide("recovery_and_replay")
    lookup = toolset.rtg_get_usage_guide("lookup_examples")
    query = toolset.rtg_get_usage_guide("query_examples")
    shapes = toolset.rtg_get_usage_guide("tool_call_shapes")
    history = toolset.rtg_get_usage_guide("migration_history")
    capabilities = toolset.rtg_get_usage_guide("capabilities")
    missing_beta_schema = toolset.rtg_get_usage_guide("life_graph_schema_v1")

    assert checklist["ok"] is True
    assert capabilities["ok"] is True
    assert len(capabilities["result"]["tools"]) == len(TOOL_NAMES)
    assert {item["name"] for item in capabilities["result"]["tools"]} == set(TOOL_NAMES)
    capability_map = {item["name"]: item for item in capabilities["result"]["tools"]}
    assert capability_map["rtg_apply_live_anchor_records"]["recommended_predecessors"] == [
        "rtg_validate_live_anchor_records"
    ]
    assert (
        capability_map["rtg_apply_live_anchor_records"]["dry_run_tool"]
        == "rtg_validate_live_anchor_records"
    )
    assert (
        capability_map["rtg_apply_live_graph_changes"]["dry_run_tool"]
        == "rtg_validate_live_graph_changes"
    )
    assert capability_map["rtg_execute_query"]["dry_run_tool"] is None
    assert capability_map["rtg_replay_ledger"]["recommended_predecessors"] == [
        "rtg_get_system_state"
    ]
    assert (
        "rtg_get_schema_pack" not in capability_map["rtg_replay_ledger"]["recommended_predecessors"]
    )
    assert workflows["ok"] is True
    assert requests["ok"] is True
    assert checklist["result"]["steps"][0]["tool"] == "rtg_validate_graph"
    assert checklist["result"]["steps"][1]["tool"] == "rtg_get_system_state"
    assert checklist["result"]["steps"][2]["arguments"] == {"topic": "everyday_life_schema"}
    assert checklist["result"]["steps"][3]["arguments"] == {"topic": "schema_staging_minimal"}
    assert any(
        step.get("arguments") == {"topic": "tool_call_shapes"}
        for step in checklist["result"]["steps"]
    )
    assert any("Every ref-like field is an object" in note for note in checklist["result"]["notes"])
    assert any(
        step.get("tool") == "rtg_resolve_anchor_by_fact" for step in checklist["result"]["steps"]
    )
    replay_check = next(
        step
        for step in checklist["result"]["steps"]
        if step.get("tool") == "rtg_verify_replay_from_ledger"
    )
    assert "domain-state equivalence" in replay_check["why"]
    assert "ledger-cursor equivalence separately" in replay_check["why"]
    assert any("rejected" in note and "failed" in note for note in checklist["result"]["notes"])
    assert missing_beta_schema["ok"] is False
    assert "schema_staging_minimal" in missing_beta_schema["error"]["message"]
    assert "life_graph_schema_v1" not in missing_beta_schema["error"]["message"]
    assert recovery["ok"] is True
    assert "<loaded snapshot>" not in json.dumps(recovery)
    assert recovery["result"]["replay_from_empty"]["arguments"] == {"replay_options": {}}
    assert recovery["result"]["steps"][-1]["tool"] == "rtg_verify_replay_from_ledger"
    assert (
        recovery["result"]["controlled_failed_migration_example"]["stage"]["tool"]
        == "rtg_stage_schema_migration"
    )
    workflow_ids = {item["workflow_id"] for item in workflows["result"]["workflows"]}
    assert {
        "connection_state_check",
        "schema_bootstrap",
        "schema_discovery",
        "data_ingest",
        "query_answer",
        "safe_update",
        "link_writing",
        "validation_error_recovery",
        "schema_evolution",
        "snapshot_replay_check",
        "staged_work_review",
        "cutover_or_abandon",
        "replay_recovery",
    } <= workflow_ids
    request_workflows = {
        workflow
        for pattern in requests["result"]["patterns"]
        for workflow in pattern["workflow_ids"]
    }
    assert {"schema_bootstrap", "data_ingest", "query_answer"} <= request_workflows
    assert lookup["ok"] is True
    assert lookup["result"]["item_by_title"]["tool"] == "rtg_execute_query"
    assert (
        lookup["result"]["resolve_anchor_by_fact_example"]["tool"] == "rtg_resolve_anchor_by_fact"
    )
    assert "lookup_examples" == lookup["result"]["topic"]
    assert query["result"]["ordered_active_items"]["arguments"]["query_options"]["order_by"]
    assert "relationship_query_guidance" in query["result"]
    assert "expected_beta_counts" not in query["result"]
    assert shapes["result"]["rtg_execute_query"]["arguments"]["query_options"] == {
        "live_filter": "live"
    }
    assert any(
        "Every ref-like field is a JSON object" in note for note in shapes["result"]["notes"]
    )
    assert shapes["result"]["rtg_validate_live_graph_changes"]["arguments"][
        "validation_options"
    ] == {"tracks": "all", "finding_limit": 20}
    assert shapes["result"]["rtg_apply_live_anchor_records"]["arguments"]["link_writes"][0] == {
        "ref": {"local_ref": "item-alpha-related-to-item-beta"},
        "type": "related_to",
        "source_ref": {"local_ref": "item-alpha"},
        "target_ref": {"local_ref": "item-beta"},
    }
    assert history["result"]["tool"] == "rtg_list_migration_history"


def test_mcp_generic_usage_guides_do_not_leak_beta_domain_terms(tmp_path: Path) -> None:
    toolset = build_empty_toolset(tmp_path)
    generic_topics = (
        "mcp_bootstrap_checklist",
        "operator_card",
        "workflow_patterns",
        "request_patterns",
        "schema_staging_minimal",
        "tool_call_shapes",
        "live_write",
        "lookup_examples",
        "query_examples",
        "recovery_and_replay",
        "migration_history",
        "migration_abandonment",
    )

    payload = json.dumps(
        {topic: toolset.rtg_get_usage_guide(topic)["result"] for topic in generic_topics},
        sort_keys=True,
    )

    for term in (
        "Vellis",
        "Person",
        "Area",
        "Project",
        "Task",
        "Note",
        "Resource",
        "Event",
        "ProjectFacts",
        "TaskFacts",
    ):
        assert term not in payload


def test_mcp_exposes_modeled_everyday_life_and_schema_design_guidance(tmp_path: Path) -> None:
    toolset = build_empty_toolset(tmp_path)
    everyday = toolset.rtg_get_usage_guide("everyday_life_schema")
    schema_design = toolset.rtg_get_usage_guide("schema_design")

    assert everyday["ok"] is True
    assert everyday["result"]["ontology_id"] == "ontology.vellis.everyday_life"
    assert {item["type_key"] for item in everyday["result"]["anchors"]} == {
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
    assert len(everyday["result"]["links"]) == 9
    assert schema_design["ok"] is True
    assert any("human approval" in step for step in schema_design["result"]["workflow"])
    assert any(
        "generic JSON blobs" in principle for principle in schema_design["result"]["principles"]
    )
    assert any(
        "allowed_values" in principle and "RE2 pattern" in principle
        for principle in schema_design["result"]["principles"]
    )


def test_mcp_toolset_stage_schema_migration_can_replace_live_schema(
    tmp_path: Path,
) -> None:
    toolset = build_toolset(tmp_path)

    staged = toolset.rtg_stage_schema_migration(
        migration_id="person-schema-v2",
        description="Replace Person schema.",
        schema_definitions=[
            {
                "kind": "anchor",
                "type_key": "Person",
                "description": "Expanded person.",
                "payload": {"required_data_types": ["Profile"]},
                "time_shape": "state_now",
            }
        ],
        retire_live_schema=[{"kind": "anchor", "type_key": "Person"}],
        response_options={"format": "full"},
    )
    cutover = toolset.rtg_apply_migration_cutover("person-schema-v2")

    migration = staged["result"]["submitted_knowledge_changes"]["migration_changes"][
        "migration_writes"
    ][0]["migration"]
    assert staged["ok"] is True
    assert len(migration["schema_make_live"]) == 1
    assert len(migration["schema_make_non_live"]) == 1
    assert cutover["ok"] is True


def test_mcp_toolset_persisted_snapshot_readback(tmp_path: Path) -> None:
    toolset = build_toolset(tmp_path)

    persisted = toolset.rtg_persist_system_snapshot("snapshots/system.json")
    listed = toolset.rtg_list_persisted_snapshots()
    loaded = toolset.rtg_load_persisted_snapshot("snapshots/system.json")
    compact_loaded = toolset.rtg_load_persisted_snapshot(
        "snapshots/system.json",
        return_snapshot=False,
    )

    assert persisted["ok"] is True
    assert listed["result"]["snapshots"][0]["relative_path"] == "snapshots/system.json"
    assert loaded["result"]["relative_path"] == "snapshots/system.json"
    assert loaded["result"]["snapshot"]["schema"]["definitions"]
    assert compact_loaded["result"]["relative_path"] == "snapshots/system.json"
    assert compact_loaded["result"]["summary"]["schema_type_counts"]["anchor"] >= 1
    assert "snapshot" not in compact_loaded["result"]


def test_mcp_toolset_replay_path_and_migration_history(tmp_path: Path) -> None:
    toolset = build_toolset(tmp_path)
    guide = toolset.rtg_get_usage_guide("schema_staging_minimal")
    staged = toolset.rtg_stage_schema_migration(
        migration_id="minimal-item-schema",
        description="Introduce minimal item schema.",
        schema_definitions=cast(
            list[dict[str, Any]],
            guide["result"]["arguments"]["schema_definitions"],
        ),
    )
    cutover = toolset.rtg_apply_migration_cutover("minimal-item-schema")
    persisted = toolset.rtg_persist_system_snapshot(
        "snapshots/after-cutover.json",
        return_snapshot=False,
    )
    verified = toolset.rtg_verify_replay_from_ledger(
        {"start_snapshot_path": "snapshots/after-cutover.json"}
    )
    history = toolset.rtg_list_migration_history()
    state = toolset.rtg_get_system_state()

    assert staged["ok"] is True
    assert cutover["ok"] is True
    assert persisted["ok"] is True
    assert verified["result"]["status"] == "replay_verified"
    assert verified["result"]["replay_window"]["start_source"] == "start_snapshot_path"
    assert state["result"]["migration_counts_scope"] == "current_migration_store"
    assert "ledger-backed migration events" in state["result"]["migration_history_hint"]
    assert [event["event_type"] for event in history["result"]["events"]] == [
        "staged",
        "cutover_applied",
    ]
    assert all(event["finding_count"] == 0 for event in history["result"]["events"])
    assert all(event["finding_codes"] == [] for event in history["result"]["events"])


def test_mcp_toolset_keeps_error_shape_for_unexpected_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    toolset = build_toolset(tmp_path)

    def raise_unexpected(self: InProcessRtgController) -> object:
        raise TypeError("unexpected controller failure")

    monkeypatch.setattr(InProcessRtgController, "export_system_snapshot", raise_unexpected)

    response = toolset.rtg_export_system_snapshot()

    assert response["ok"] is False
    assert response["error"]["type"] == "TypeError"
    assert response["error"]["message"] == "unexpected controller failure"


def test_mcp_toolset_rejects_unsupported_controller_options(tmp_path: Path) -> None:
    toolset = build_toolset(tmp_path)
    snapshot = toolset.rtg_export_system_snapshot()["result"]

    missing_cutover = toolset.rtg_apply_migration_cutover("missing")
    bad_cutover = toolset.rtg_apply_migration_cutover(
        "missing",
        {"validation_mode": "relaxed"},
    )
    bad_discovery = toolset.rtg_discover_anchor_types({"limit": 0})
    bad_restore = toolset.rtg_restore_from_snapshot(snapshot, {"ledger_mode": "silent"})
    bad_validation_options = toolset.rtg_validate_live_graph_changes(
        {},
        {"mode": "strict"},
    )
    nested_query_options = toolset.rtg_execute_query(
        {"anchor_buckets": [], "query_options": {"live_filter": "live"}},
    )
    nested_response_options = toolset.rtg_execute_query(
        {"anchor_buckets": [], "response_options": {"format": "properties_only"}},
    )
    bad_response_options = toolset.rtg_execute_query(
        {"anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}]},
        response_options={"mode": "compact"},
    )

    assert missing_cutover["ok"] is False
    assert missing_cutover["error"]["type"] == "RtgControllerPreconditionFailed"
    assert bad_cutover["ok"] is False
    assert bad_cutover["error"]["type"] == "RtgControllerPreconditionFailed"
    assert "validation_mode" in bad_cutover["error"]["message"]
    assert bad_discovery["ok"] is False
    assert bad_discovery["error"]["type"] == "RtgControllerDiscoveryFailed"
    assert bad_restore["ok"] is False
    assert bad_restore["error"]["type"] == "RtgControllerSnapshotFailed"
    assert bad_validation_options["ok"] is False
    assert (
        "dry-run tools do not accept validation_options.mode"
        in bad_validation_options["error"]["message"]
    )
    assert "top-level validation_mode" in bad_validation_options["error"]["message"]
    assert bad_validation_options["error"]["diagnostic"]["code"] == "mcp.input.unsupported_field"
    assert bad_validation_options["error"]["diagnostic"]["path"] == "validation_options.mode"
    assert bad_validation_options["error"]["diagnostic"]["guide_topics"] == [
        "tool_call_shapes",
        "live_write",
    ]
    assert nested_query_options["ok"] is False
    assert (
        "top-level rtg_execute_query argument query_options"
        in nested_query_options["error"]["message"]
    )
    assert nested_query_options["error"]["diagnostic"]["path"] == "query_spec.query_options"
    assert nested_query_options["error"]["diagnostic"]["minimal_example"]["query_options"] == {
        "live_filter": "live"
    }
    assert nested_response_options["ok"] is False
    assert (
        "top-level rtg_execute_query argument response_options"
        in nested_response_options["error"]["message"]
    )
    assert nested_response_options["error"]["diagnostic"]["path"] == "query_spec.response_options"
    assert bad_response_options["ok"] is False
    assert "Accepted field(s): 'format'" in bad_response_options["error"]["message"]
    assert '{"format": "properties_only"}' in bad_response_options["error"]["message"]
    assert bad_response_options["error"]["diagnostic"]["accepted_fields"] == ["format"]
    assert bad_response_options["error"]["diagnostic"]["guide_topics"] == [
        "tool_call_shapes",
        "query_examples",
    ]


def test_mcp_toolset_errors_include_ref_and_uuid_diagnostics(tmp_path: Path) -> None:
    toolset = build_toolset(tmp_path)

    missing_ref = toolset.rtg_apply_live_graph_changes({"anchor_writes": [{"type": "Person"}]})
    string_ref = toolset.rtg_apply_live_graph_changes(
        {"anchor_writes": [{"ref": "person", "type": "Person"}]}
    )
    bad_finding_limit = toolset.rtg_validate_live_graph_changes(
        {},
        {"finding_limit": "many"},
    )
    bad_uuid = toolset.rtg_stage_knowledge_changes(
        {
            "migration_changes": {
                "migration_writes": [
                    {
                        "ref": {"resource_id": "migration-1"},
                        "migration": {
                            "migration_id": "migration-1",
                            "description": "Bad UUID list.",
                            "status": "ready",
                            "schema_make_live": ["not-a-uuid"],
                        },
                    }
                ]
            }
        }
    )

    assert missing_ref["ok"] is False
    assert missing_ref["error"]["diagnostic"]["code"] == "mcp.input.required_field"
    assert missing_ref["error"]["diagnostic"]["path"] == "anchor_writes.ref"
    assert string_ref["ok"] is False
    assert string_ref["error"]["diagnostic"]["code"] == "mcp.input.ref_shape"
    assert string_ref["error"]["diagnostic"]["guide_topics"] == [
        "workflow_patterns",
        "live_write",
        "lookup_examples",
    ]
    assert bad_finding_limit["ok"] is False
    assert bad_finding_limit["error"]["diagnostic"]["code"] == "mcp.input.type_mismatch"
    assert bad_finding_limit["error"]["diagnostic"]["path"] == "validation_options.finding_limit"
    assert bad_uuid["ok"] is False
    assert bad_uuid["error"]["diagnostic"]["code"] == "mcp.input.uuid"
    assert bad_uuid["error"]["diagnostic"]["guide_topics"] == [
        "schema_staging_minimal",
        "tool_call_shapes",
    ]


def test_diagnostic_json_normalization_preserves_nested_sequences() -> None:
    diagnostic = diagnostic_as_json(
        {
            "code": "example",
            "accepted_fields": ("alpha", "beta"),
            "minimal_example": {"path": (["facts", ("title",)],)},
            "ignored": object(),
        }
    )

    assert diagnostic == {
        "code": "example",
        "accepted_fields": ["alpha", "beta"],
        "minimal_example": {"path": [["facts", ["title"]]]},
    }


def test_mcp_tool_metadata_is_concise_complete_and_annotated() -> None:
    entries = mcp_tool_metadata()
    metadata = {item["name"]: item for item in entries}

    assert len(metadata) == len(TOOL_NAMES) == 27
    assert "rtg_get_agent_affordance_eval_prompt" not in metadata
    assert sum(len(item["description"].encode("utf-8")) for item in entries) <= 5 * 1024
    assert all("Lane:" in item["description"] for item in entries)
    assert metadata["rtg_execute_query"]["annotations"] == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert metadata["rtg_apply_live_graph_changes"]["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    }


def test_mcp_server_stdio_protocol_lists_tools_from_non_repo_cwd(tmp_path: Path) -> None:
    async def run_protocol_check() -> None:
        repo_root = Path(__file__).resolve().parents[3]
        params = StdioServerParameters(
            command="uv",
            args=[
                "--directory",
                str(repo_root),
                "run",
                "python",
                "-m",
                "apps.rtg_knowledge_graph",
                "serve-mcp",
                "--transport",
                "stdio",
                "--storage-root",
                str(tmp_path / "protocol-storage"),
            ],
            cwd=tmp_path,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                serialized_tools = json.dumps(
                    [
                        tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                        for tool in tools.tools
                    ],
                    separators=(",", ":"),
                )
                description_bytes = sum(
                    len((tool.description or "").encode("utf-8")) for tool in tools.tools
                )
                result = await session.call_tool("rtg_validate_graph", {})

        payload = _tool_result_payload(result)

        assert len(tool_names) == len(TOOL_NAMES)
        assert len(serialized_tools.encode("utf-8")) <= 16 * 1024
        assert description_bytes <= 5 * 1024
        assert "rtg_validate_graph" in tool_names
        assert "rtg_get_agent_affordance_eval_prompt" not in tool_names
        assert result.isError is False
        assert payload["ok"] is True
        assert payload["result"]["accepted"] is True

    asyncio.run(run_protocol_check())


def test_mcp_server_http_protocol_lists_tools_from_non_repo_cwd(tmp_path: Path) -> None:
    async def run_protocol_check() -> None:
        repo_root = Path(__file__).resolve().parents[3]
        port = _free_tcp_port()
        process = subprocess.Popen(
            [
                "uv",
                "--directory",
                str(repo_root),
                "run",
                "python",
                "-m",
                "apps.rtg_knowledge_graph",
                "serve-mcp",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--path",
                "/mcp",
                "--storage-root",
                str(tmp_path / "http-protocol-storage"),
            ],
            cwd=tmp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_for_tcp_port("127.0.0.1", port, process)
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (
                read,
                write,
                _get_session_id,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    tool_names = {tool.name for tool in tools.tools}
                    result = await session.call_tool("rtg_validate_graph", {})
        finally:
            _terminate_process(process)

        payload = _tool_result_payload(result)

        assert len(tool_names) == len(TOOL_NAMES)
        assert "rtg_validate_graph" in tool_names
        assert result.isError is False
        assert payload["ok"] is True
        assert payload["result"]["accepted"] is True

    asyncio.run(run_protocol_check())


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_tcp_port(host: str, port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(f"MCP HTTP server exited early: {stderr}")
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    _terminate_process(process)
    raise AssertionError(f"MCP HTTP server did not listen on {host}:{port}")


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _skill_json_block_after(text: str, marker: str) -> dict[str, Any]:
    section_start = text.index(marker)
    match = re.search(r"```json\n(.*?)\n```", text[section_start:], flags=re.DOTALL)
    if match is None:
        raise AssertionError(f"missing JSON block after {marker!r}")
    return cast(dict[str, Any], json.loads(match.group(1)))


def _tool_result_payload(result: object) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return cast(dict[str, Any], structured)
    content = cast(Any, result).content
    text = content[0].text
    return cast(dict[str, Any], json.loads(text))
