from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from apps.rtg_federation.registry_io import load_bridge_store
from apps.rtg_federation.tests.support import seed_repo_component_snapshot
from tools.rtg_graph_registry import init_graph_payload, load_registry, main, mcp_info_payload


def repo_metadata() -> dict[str, object]:
    return {
        "snapshot_path": "snapshots/test.json",
        "federated_read_capabilities": [
            {
                "query_name": "repo_components_evidence_status",
                "implementation": (
                    "apps.rtg_federation.queries.repo_components_evidence_status:CANNED_QUERY"
                ),
                "description": "Summarize component evidence status from the repo twin.",
                "terms": ["component", "components", "spec", "specs", "evidence", "repo"],
                "domains": ["components", "evidence"],
                "tags": ["repo"],
            }
        ],
        "citation_projection": {
            "query_name": "repo_components_evidence_status",
            "anchor_bucket": "component",
        },
        "route_pack_read": {
            "query_name": "repo_components_evidence_status",
            "command": "just graph-query untested",
            "verification_commands": ["just graph-check"],
            "stale_recovery_command": "just graph-verify",
            "required_docs": [],
        },
    }


def write_registry(path: Path, *, graph_root: Path | None = None) -> None:
    repo_root = graph_root or Path(".data/repo-twin")
    path.write_text(
        json.dumps(
            {
                "graphs": [
                    {
                        "graph_id": "repo_twin",
                        "title": "Repo Digital Twin",
                        "storage_root": str(repo_root),
                        "sql_database_path": str(repo_root / "controller.sqlite"),
                        "authority": "derived_from_repo",
                        "write_policy": "sync_only",
                        "domains": ["components", "evidence"],
                        "tags": ["repo"],
                        "mcp_endpoint": {
                            "transport": "http",
                            "host": "127.0.0.1",
                            "port": 8765,
                            "path": "/mcp",
                            "server_name": "vellis_repo_twin",
                        },
                        "metadata": repo_metadata(),
                    },
                    {
                        "graph_id": "personal_ops",
                        "title": "Personal Operating Graph",
                        "storage_root": ".data/monographs/personal-ops-v1",
                        "sql_database_path": ".data/monographs/personal-ops-v1/controller.sqlite",
                        "authority": "user_authored",
                        "write_policy": "explicit_target_required",
                        "domains": ["decisions", "evidence"],
                        "tags": ["personal"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def write_bridge_catalog(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "bridges": [
                    {
                        "bridge_type": "related_context",
                        "source": {
                            "graph_id": "repo_twin",
                            "local_uuid": "11111111-1111-4111-8111-111111111111",
                        },
                        "target": {
                            "graph_id": "personal_ops",
                            "local_uuid": "22222222-2222-4222-8222-222222222222",
                        },
                        "confidence": 0.66,
                        "asserted_at": "2026-07-09T00:00:00Z",
                        "asserted_by": "agent.codex",
                        "provenance": [
                            {
                                "graph_id": "repo_twin",
                                "local_uuid": "33333333-3333-4333-8333-333333333333",
                            }
                        ],
                    }
                ],
                "candidates": [
                    {
                        "bridge_type": "related_context",
                        "source": {
                            "graph_id": "repo_twin",
                            "local_uuid": "44444444-4444-4444-8444-444444444444",
                        },
                        "target": {
                            "graph_id": "personal_ops",
                            "local_uuid": "55555555-5555-4555-8555-555555555555",
                        },
                        "confidence": 0.48,
                        "proposed_at": "2026-07-09T00:00:00Z",
                        "proposed_by": "agent.codex",
                        "evidence": [
                            {
                                "graph_id": "repo_twin",
                                "local_uuid": "66666666-6666-4666-8666-666666666666",
                            }
                        ],
                        "rationale": "candidate requires review",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def write_candidate_catalog(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "bridges": [],
                "candidates": [
                    {
                        "bridge_type": "related_context",
                        "source": {
                            "graph_id": "repo_twin",
                            "local_uuid": "44444444-4444-4444-8444-444444444444",
                        },
                        "target": {
                            "graph_id": "personal_ops",
                            "local_uuid": "55555555-5555-4555-8555-555555555555",
                        },
                        "confidence": 0.48,
                        "proposed_at": "2026-07-09T00:00:00Z",
                        "proposed_by": "agent.codex",
                        "evidence": [
                            {
                                "graph_id": "repo_twin",
                                "local_uuid": "66666666-6666-4666-8666-666666666666",
                            }
                        ],
                        "rationale": "candidate requires review",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_registry_tool_loads_json_and_renders_mcp_info(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)

    registry = load_registry(registry_path)
    payload = mcp_info_payload(registry, "repo_twin")

    assert payload["graph"]["graph_id"] == "repo_twin"
    assert payload["client_config"] == {
        "mcpServers": {
            "vellis_repo_twin": {
                "transport": "http",
                "url": "http://127.0.0.1:8765/mcp",
            }
        }
    }
    assert "--storage-root" in payload["launch"]["args"]


def test_registry_tool_route_command_prints_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "route",
            "--operation",
            "read",
            "--json",
            "Which components have evidence?",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["selected_graph_id"] == "repo_twin"
    assert output["requires_confirmation"] is False


def test_registry_tool_federated_plan_command_prints_json(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_bridge_catalog(bridge_path)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-plan",
            "--bridges",
            str(bridge_path),
            "--json",
            "Compare component evidence with personal decisions.",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["executable"] is True
    assert [step["graph_id"] for step in output["steps"]] == ["personal_ops", "repo_twin"]
    assert output["cross_graph_reference_rule"] == (
        "references must carry canonical (graph_id, local_uuid) identity"
    )
    assert output["bridge_hints"]["matching_bridge_count"] == 1
    assert output["bridge_hints"]["join_execution"] == "not_performed"
    assert output["bridge_hints"]["candidate_hints"]["status"] == ("suppressed_by_confirmed_bridge")
    checklist = output["bridge_hints"]["follow_up_checklist"][0]
    assert [item["action"] for item in checklist["items"]] == [
        "graph_local_read",
        "graph_local_read",
        "synthesize_outside_graph",
    ]
    assert checklist["items"][0]["graph_id"] == "repo_twin"
    assert checklist["items"][1]["graph_id"] == "personal_ops"


def test_registry_tool_route_pack_preview_command_prints_json(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_bridge_catalog(bridge_path)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "route-pack-preview",
            "--bridges",
            str(bridge_path),
            "--json",
            "Compare component evidence with personal decisions.",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["selected_skill"]["name"] == "rtg-federation-control-plane"
    assert output["selected_skill"]["handoff_chain"][0]["name"] == "rtg-knowledge-graph-mcp"
    assert "vellis_route_pack_preview" in output["scoped_tools"]["federation_mcp_tools"]
    assert [context["graph_id"] for context in output["graph_contexts"]] == [
        "personal_ops",
        "repo_twin",
    ]
    assert output["identity_and_citation_rules"]["canonical_identity"] == ("(graph_id, local_uuid)")
    assert output["freshness_and_evidence"]["preflight"]["status"] == "failed"
    assert any(hazard["code"] == "preflight_not_ready" for hazard in output["hazards"])


def test_registry_tool_route_pack_gate_command_prints_json_and_checks_decision(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_bridge_catalog(bridge_path)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "route-pack-gate",
            "--bridges",
            str(bridge_path),
            "--json",
            "Compare component evidence with personal decisions.",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    checked_exit_code = main(
        [
            "--registry",
            str(registry_path),
            "route-pack-gate",
            "--bridges",
            str(bridge_path),
            "--check",
            "Compare component evidence with personal decisions.",
        ]
    )
    capsys.readouterr()

    assert exit_code == 0
    assert checked_exit_code == 1
    assert output["decision"] == "blocked"
    assert output["selected_skill"]["name"] == "rtg-federation-control-plane"
    assert output["graph_targets"]["graph_context_ids"] == ["personal_ops", "repo_twin"]
    assert "preflight_not_ready" in output["blocking_hazard_codes"]
    assert "vellis_route_pack_gate" in output["allowed_tools"]["federation_mcp_tools"]
    assert output["allowed_tools"]["graph_local_mcp_tools_after_selection"] == []


def test_registry_tool_route_pack_gate_prints_descriptor_read_commands(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "route-pack-gate",
            "Which component specs lack evidence?",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "graph_context_ids=repo_twin" in output
    assert "next_action=execute_descriptor_read" in output
    assert "command=just graph-query untested" in output
    assert "stale_recovery_command=just graph-verify" in output


def test_registry_tool_federated_plan_surfaces_candidate_hints(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_candidate_catalog(bridge_path)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-plan",
            "--bridges",
            str(bridge_path),
            "--json",
            "Compare component evidence with personal decisions.",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    candidate_hints = output["bridge_hints"]["candidate_hints"]
    assert output["bridge_hints"]["matching_bridge_count"] == 0
    assert candidate_hints["status"] == "candidate_only"
    assert candidate_hints["matching_candidate_count"] == 1
    assert candidate_hints["traversal_permission"] is False
    assert candidate_hints["candidates"][0]["confidence"] == 0.48


def test_registry_tool_federated_capabilities_command_prints_json(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-capabilities",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["graph_count"] == 2
    assert output["ready_capability_count"] == 1
    repo_capabilities = [graph for graph in output["graphs"] if graph["graph_id"] == "repo_twin"][0]
    assert repo_capabilities["status"] == "ready"
    assert repo_capabilities["capabilities"][0]["query_name"] == ("repo_components_evidence_status")
    assert repo_capabilities["capabilities"][0]["implementation"] == (
        "apps.rtg_federation.queries.repo_components_evidence_status:CANNED_QUERY"
    )


def test_registry_tool_federated_capabilities_check_passes(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-capabilities",
            "--check",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["check"]["status"] == "passed"
    assert output["check"]["failed_graph_ids"] == []


def test_registry_tool_federated_preflight_check_passes(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-preflight",
            "--check",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["ready_graph_count"] == 1
    assert output["skipped_graph_count"] == 1


def test_registry_tool_federated_preflight_check_fails_for_missing_snapshot(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=tmp_path / "missing-repo-twin")

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-preflight",
            "--check",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["status"] == "failed"
    assert output["not_ready_graph_ids"] == ["repo_twin"]


def test_registry_tool_federated_capabilities_check_fails_for_broken_implementation(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    capability = payload["graphs"][0]["metadata"]["federated_read_capabilities"][0]
    capability["implementation"] = "apps.rtg_federation.queries.missing:CANNED_QUERY"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-capabilities",
            "--check",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["check"]["status"] == "failed"
    assert output["check"]["failed_graph_ids"] == ["repo_twin"]
    repo_capabilities = [graph for graph in output["graphs"] if graph["graph_id"] == "repo_twin"][0]
    assert repo_capabilities["status"] == "no_ready_capabilities"
    assert repo_capabilities["capabilities"][0]["status"] == "unknown_query"


def test_registry_tool_federated_capability_template_prints_json(
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    exit_code = main(
        [
            "federated-capability-template",
            "gothic_source_index",
            "--term",
            "gothic",
            "--domain",
            "literature",
            "--tag",
            "archive",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["descriptor"]["query_name"] == "gothic_source_index"
    assert output["descriptor"]["implementation"] == (
        "apps.rtg_federation.queries.gothic_source_index:CANNED_QUERY"
    )
    assert output["descriptor"]["terms"] == ["gothic"]
    assert output["descriptor"]["domains"] == ["literature"]
    assert output["descriptor"]["tags"] == ["archive"]
    assert output["module_path"] == "apps/rtg_federation/queries/gothic_source_index.py"
    assert 'name="gothic_source_index"' in output["module_template"]


def test_registry_tool_federated_answer_command_prints_json(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path, graph_root=graph_root)
    write_bridge_catalog(bridge_path)

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-answer",
            "--bridges",
            str(bridge_path),
            "--json",
            "Compare component evidence with personal decisions.",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "partial"
    assert output["synthesis"]["answer"]["executed_graph_count"] == 1
    assert output["synthesis"]["answer"]["planned_graph_count"] == 2
    citation_uuids = {citation["local_uuid"] for citation in output["synthesis"]["citations"]}
    repo_read = [read for read in output["synthesis"]["reads"] if read["graph_id"] == "repo_twin"][
        0
    ]
    answer_uuids = {
        component["local_uuid"] for component in repo_read["summary"]["answer"]["components"]
    }
    assert citation_uuids == answer_uuids
    assert len(citation_uuids) == 2
    assert all(UUID(value) for value in citation_uuids)
    assert output["join_execution"] == "not_performed"


def test_registry_tool_resolve_citation_command_prints_json(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    answer_exit_code = main(
        [
            "--registry",
            str(registry_path),
            "federated-answer",
            "--target-graph-id",
            "repo_twin",
            "--json",
            "Which component specs lack evidence?",
        ]
    )
    answer = json.loads(capsys.readouterr().out)
    citation = answer["synthesis"]["citations"][0]

    resolve_exit_code = main(
        [
            "--registry",
            str(registry_path),
            "resolve-citation",
            citation["graph_id"],
            citation["local_uuid"],
            "--json",
        ]
    )

    resolved = json.loads(capsys.readouterr().out)
    assert answer_exit_code == 0
    assert resolve_exit_code == 0
    assert resolved["status"] == "resolved"
    assert resolved["graph_id"] == "repo_twin"
    assert resolved["local_uuid"] == citation["local_uuid"]
    assert resolved["records"]
    assert {record["anchors"]["component"] for record in resolved["records"]} == {
        citation["local_uuid"]
    }


def test_registry_tool_bridge_traverse_command_prints_json(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path, graph_root=graph_root)
    main(
        [
            "--registry",
            str(registry_path),
            "federated-answer",
            "--target-graph-id",
            "repo_twin",
            "--json",
            "Which component specs lack evidence?",
        ]
    )
    answer = json.loads(capsys.readouterr().out)
    citation = answer["synthesis"]["citations"][0]
    bridge_path.write_text(
        json.dumps(
            {
                "bridges": [
                    {
                        "bridge_type": "related_context",
                        "source": citation,
                        "target": {
                            "graph_id": "personal_ops",
                            "local_uuid": "22222222-2222-4222-8222-222222222222",
                        },
                        "confidence": 0.8,
                        "asserted_at": "2026-07-10T00:00:00Z",
                        "asserted_by": "agent.codex",
                        "provenance": [citation],
                    }
                ],
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )
    bridge_id = load_bridge_store(bridge_path).list_bridges().bridges[0].bridge_id

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "bridge-traverse",
            "--bridges",
            str(bridge_path),
            bridge_id,
            "--json",
        ]
    )

    traversed = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert traversed["status"] == "partial"
    assert traversed["bridge"]["bridge_id"] == bridge_id
    assert traversed["source"]["resolution"]["status"] == "resolved"
    assert traversed["target"]["resolution"]["status"] == "unsupported"
    assert traversed["join_execution"] == "not_performed"


def test_registry_tool_lists_inspects_and_promotes_bridge_candidate(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_candidate_catalog(bridge_path)

    list_exit_code = main(
        [
            "--registry",
            str(registry_path),
            "bridge-candidates",
            "--bridges",
            str(bridge_path),
            "list",
            "--json",
        ]
    )
    listed = json.loads(capsys.readouterr().out)
    candidate_id = listed["candidates"][0]["candidate_id"]
    inspect_exit_code = main(
        [
            "--registry",
            str(registry_path),
            "bridge-candidates",
            "--bridges",
            str(bridge_path),
            "inspect",
            candidate_id,
            "--json",
        ]
    )
    inspected = json.loads(capsys.readouterr().out)
    promote_exit_code = main(
        [
            "--registry",
            str(registry_path),
            "bridge-candidates",
            "--bridges",
            str(bridge_path),
            "promote",
            candidate_id,
            "--asserted-at",
            "2026-07-09T01:00:00Z",
            "--asserted-by",
            "agent.codex",
            "--json",
        ]
    )
    promoted = json.loads(capsys.readouterr().out)
    catalog = json.loads(bridge_path.read_text(encoding="utf-8"))

    assert list_exit_code == 0
    assert inspect_exit_code == 0
    assert promote_exit_code == 0
    assert inspected["candidate"]["candidate_id"] == candidate_id
    assert promoted["candidate"]["status"] == "promoted"
    assert promoted["bridge"]["metadata"]["promoted_from_candidate_id"] == candidate_id
    assert len(catalog["bridges"]) == 1
    assert catalog["candidates"][0]["status"] == "promoted"


def test_registry_tool_rejects_bridge_candidate(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_candidate_catalog(bridge_path)

    main(
        [
            "--registry",
            str(registry_path),
            "bridge-candidates",
            "--bridges",
            str(bridge_path),
            "list",
            "--json",
        ]
    )
    candidate_id = json.loads(capsys.readouterr().out)["candidates"][0]["candidate_id"]
    reject_exit_code = main(
        [
            "--registry",
            str(registry_path),
            "bridge-candidates",
            "--bridges",
            str(bridge_path),
            "reject",
            candidate_id,
            "--rejected-at",
            "2026-07-09T01:00:00Z",
            "--rejected-by",
            "agent.codex",
            "--reason",
            "candidate evidence did not support traversal",
            "--json",
        ]
    )
    rejected = json.loads(capsys.readouterr().out)
    catalog = json.loads(bridge_path.read_text(encoding="utf-8"))

    assert reject_exit_code == 0
    assert rejected["candidate"]["status"] == "rejected"
    assert rejected["candidate"]["rejection_reason"] == (
        "candidate evidence did not support traversal"
    )
    assert catalog["bridges"] == []
    assert catalog["candidates"][0]["status"] == "rejected"


def test_registry_tool_init_creates_and_validates_graph_root(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    graph_root = tmp_path / "repo-twin"
    registry_path.write_text(
        json.dumps(
            {
                "graphs": [
                    {
                        "graph_id": "repo_twin",
                        "title": "Repo Digital Twin",
                        "storage_root": str(graph_root),
                        "sql_database_path": str(graph_root / "controller.sqlite"),
                        "authority": "derived_from_repo",
                        "write_policy": "sync_only",
                        "domains": ["components", "evidence"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = init_graph_payload(load_registry(registry_path), "repo_twin")

    assert payload["graph"]["graph_id"] == "repo_twin"
    assert payload["app"]["rtg_controller_ready"] is True
    assert payload["validation"]["ok"] is True
    assert payload["validation"]["result"]["accepted"] is True
    assert (graph_root / "system" / "app_manifest.json").is_file()


def test_registry_tool_route_query_canned_command_prints_json(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "graphs": [
                    {
                        "graph_id": "repo_twin",
                        "title": "Repo Digital Twin",
                        "storage_root": str(graph_root),
                        "sql_database_path": str(graph_root / "controller.sqlite"),
                        "authority": "derived_from_repo",
                        "write_policy": "sync_only",
                        "domains": ["components", "specs", "evidence"],
                        "metadata": {"snapshot_path": "snapshots/test.json"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "route-query",
            "--canned-query",
            "repo_components_evidence_status",
            "--json",
            "Which component specs lack evidence?",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["answer"]["missing_evidence_component_ids"] == ["component.without_evidence"]
