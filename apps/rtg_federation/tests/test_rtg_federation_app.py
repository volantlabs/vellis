from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from apps.rtg_federation.main import main
from apps.rtg_federation.mcp_server import mcp_dry_run_status
from apps.rtg_federation.queries import personal_attention_overview
from apps.rtg_federation.registry_io import load_bridge_store, load_registry
from apps.rtg_federation.tests.support import (
    seed_personal_ops_snapshot,
    seed_repo_component_snapshot,
)
from apps.rtg_federation.toolset import RtgFederationToolset
from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset
from components.rtg.change_validation import DeterministicRtgChangeValidator
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import InProcessRtgController
from components.rtg.evidence_bounded_synthesis import (
    RtgEvidenceBoundedSynthesisRequest,
    RtgEvidenceCitationRef,
    RtgSemanticClaimDraft,
    RtgSemanticSynthesisDraft,
)
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.graph_bridge import (
    InMemoryRtgGraphBridge,
    RtgGraphBridgeDraft,
    RtgGraphLocalReference,
)
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

MODEL_EVIDENCE = {
    "RtgFederationCompositionVerification": (
        "test_federation_toolset_lists_routes_and_returns_graph_mcp_info",
        "test_federation_toolset_returns_structured_federated_answer",
        "test_federation_toolset_traverses_one_active_bridge_without_joining",
        "test_federation_toolset_returns_evidence_bounded_semantic_answer",
        "test_federation_mcp_dry_run_reports_control_plane_metadata",
    ),
}


def repo_metadata(*, include_read_capability: bool = True) -> dict[str, Any]:
    metadata: dict[str, Any] = {"snapshot_path": "snapshots/test.json"}
    if include_read_capability:
        metadata["federated_read_capabilities"] = [
            {
                "query_name": "repo_components_evidence_status",
                "implementation": (
                    "apps.rtg_federation.queries.repo_components_evidence_status:CANNED_QUERY"
                ),
                "description": "Summarize component evidence status from the repo twin.",
                "terms": ["component", "components", "spec", "specs", "evidence", "repo"],
                "domains": ["components", "specs", "evidence"],
                "tags": ["repo"],
            }
        ]
        metadata["citation_projection"] = {
            "query_name": "repo_components_evidence_status",
            "anchor_bucket": "component",
        }
        metadata["route_pack_read"] = {
            "query_name": "repo_components_evidence_status",
            "command": "just graph-query untested",
            "verification_commands": ["just graph-check"],
            "stale_recovery_command": "just graph-verify",
            "required_docs": [],
        }
    return metadata


def personal_ops_metadata(*, include_read_capability: bool = False) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "schema_domain": "personal_operating_graph",
        "snapshot_path": "snapshots/test.json",
    }
    if include_read_capability:
        metadata["federated_read_capabilities"] = [
            {
                "query_name": "personal_attention_overview",
                "implementation": (
                    "apps.rtg_federation.queries.personal_attention_overview:CANNED_QUERY"
                ),
                "description": "Summarize personal operating graph items that need attention.",
                "terms": [
                    "attention",
                    "this week",
                    "commitments",
                    "routines",
                    "decisions",
                    "evidence gaps",
                ],
                "domains": ["commitments", "decisions", "routines", "attention", "evidence"],
                "tags": ["personal", "operating", "memory", "this week"],
            }
        ]
        metadata["citation_projection"] = {
            "query_name": "personal_attention_overview",
            "anchor_bucket": "item",
        }
    return metadata


def write_registry(
    path: Path,
    *,
    graph_root: Path | None = None,
    personal_graph_root: Path | None = None,
    include_read_capability: bool = True,
    include_personal_read_capability: bool = False,
) -> None:
    repo_root = graph_root or Path(".data/repo-twin")
    personal_root = personal_graph_root or Path(".data/monographs/personal-ops-v1")
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
                        "domains": ["components", "specs", "evidence"],
                        "tags": ["repo"],
                        "mcp_endpoint": {
                            "transport": "http",
                            "host": "127.0.0.1",
                            "port": 8765,
                            "path": "/mcp",
                            "server_name": "vellis_repo_twin",
                        },
                        "metadata": repo_metadata(include_read_capability=include_read_capability),
                    },
                    {
                        "graph_id": "personal_ops",
                        "title": "Personal Operating Graph",
                        "storage_root": str(personal_root),
                        "sql_database_path": str(personal_root / "controller.sqlite"),
                        "authority": "user_authored",
                        "write_policy": "explicit_target_required",
                        "domains": [
                            "commitments",
                            "decisions",
                            "routines",
                            "attention",
                            "evidence",
                        ],
                        "tags": ["personal", "operating", "memory", "this week"],
                        "metadata": personal_ops_metadata(
                            include_read_capability=include_personal_read_capability
                        ),
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
                        "metadata": {"label": "Repo evidence can inform personal decisions"},
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


def test_federation_toolset_lists_routes_and_returns_graph_mcp_info(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_bridge_catalog(bridge_path)
    toolset = RtgFederationToolset(
        load_registry(registry_path),
        load_bridge_store(bridge_path),
    )

    listed = toolset.vellis_list_graphs()
    capabilities = toolset.vellis_federated_capabilities()
    route = toolset.vellis_intent_compile(text="Which component specs lack evidence?")
    route_pack = toolset.vellis_route_pack_preview(
        text="Compare component evidence with personal decisions."
    )
    route_gate = toolset.vellis_route_pack_gate(
        text="Compare component evidence with personal decisions."
    )
    plan = toolset.vellis_federated_plan(text="Compare component evidence with personal decisions.")
    write_route = toolset.vellis_intent_compile(
        operation="write",
        text="Record evidence for a decision.",
    )
    mcp_info = toolset.vellis_graph_mcp_info("repo_twin")

    assert listed["ok"] is True
    assert [graph["graph_id"] for graph in listed["result"]["graphs"]] == [
        "personal_ops",
        "repo_twin",
    ]
    assert capabilities["ok"] is True
    assert capabilities["result"]["ready_capability_count"] == 1
    repo_capabilities = [
        graph for graph in capabilities["result"]["graphs"] if graph["graph_id"] == "repo_twin"
    ][0]
    assert repo_capabilities["status"] == "ready"
    assert repo_capabilities["capabilities"][0]["query_name"] == ("repo_components_evidence_status")
    assert repo_capabilities["capabilities"][0]["implementation"] == (
        "apps.rtg_federation.queries.repo_components_evidence_status:CANNED_QUERY"
    )
    assert repo_capabilities["capabilities"][0]["resolved_implementation"] == (
        "apps.rtg_federation.queries.repo_components_evidence_status:CANNED_QUERY"
    )
    assert route["ok"] is True
    assert route["result"]["selected_graph_id"] == "repo_twin"
    assert route_pack["ok"] is True
    assert route_pack["result"]["selected_skill"]["name"] == "rtg-federation-control-plane"
    assert route_pack["result"]["selected_skill"]["handoff_chain"][0]["name"] == (
        "rtg-knowledge-graph-mcp"
    )
    assert [context["graph_id"] for context in route_pack["result"]["graph_contexts"]] == [
        "personal_ops",
        "repo_twin",
    ]
    assert (
        "vellis_route_pack_preview" in route_pack["result"]["scoped_tools"]["federation_mcp_tools"]
    )
    assert "just rtg-federation-preflight" in [
        item["command"] for item in route_pack["result"]["verification_commands"]
    ]
    assert any(
        hazard["code"] == "missing_mcp_endpoint" for hazard in route_pack["result"]["hazards"]
    )
    assert route_pack["result"]["identity_and_citation_rules"]["canonical_identity"] == (
        "(graph_id, local_uuid)"
    )
    assert route_gate["ok"] is True
    assert route_gate["result"]["decision"] == "blocked"
    assert route_gate["result"]["selected_skill"]["name"] == "rtg-federation-control-plane"
    assert route_gate["result"]["graph_targets"]["graph_context_ids"] == [
        "personal_ops",
        "repo_twin",
    ]
    assert "preflight_not_ready" in route_gate["result"]["blocking_hazard_codes"]
    assert "missing_mcp_endpoint" in route_gate["result"]["clarification_hazard_codes"]
    assert route_gate["result"]["allowed_tools"]["graph_local_mcp_tools_after_selection"] == []
    assert plan["ok"] is True
    assert plan["result"]["executable"] is True
    assert [step["graph_id"] for step in plan["result"]["steps"]] == [
        "personal_ops",
        "repo_twin",
    ]
    assert (
        plan["result"]["cross_graph_reference_rule"]
        == "references must carry canonical (graph_id, local_uuid) identity"
    )
    assert plan["result"]["bridge_hints"]["matching_bridge_count"] == 1
    assert plan["result"]["bridge_hints"]["join_execution"] == "not_performed"
    assert plan["result"]["bridge_hints"]["candidate_hints"]["status"] == (
        "suppressed_by_confirmed_bridge"
    )
    assert plan["result"]["bridge_hints"]["candidate_hints"]["traversal_permission"] is False
    assert plan["result"]["bridge_hints"]["bridges"][0]["source"] == {
        "graph_id": "repo_twin",
        "local_uuid": "11111111-1111-4111-8111-111111111111",
    }
    checklist = plan["result"]["bridge_hints"]["follow_up_checklist"][0]
    assert checklist["status"] == "planned_not_executed"
    assert [item["action"] for item in checklist["items"]] == [
        "graph_local_read",
        "graph_local_read",
        "synthesize_outside_graph",
    ]
    assert checklist["items"][0]["graph_id"] == "repo_twin"
    assert checklist["items"][1]["graph_id"] == "personal_ops"
    assert all(item["executed"] is False for item in checklist["items"])
    assert write_route["ok"] is True
    assert write_route["result"]["selected_graph_id"] is None
    assert write_route["result"]["requires_confirmation"] is True
    assert mcp_info["ok"] is True
    assert mcp_info["result"]["client_config"]["mcpServers"]["vellis_repo_twin"]["url"] == (
        "http://127.0.0.1:8765/mcp"
    )


def test_route_pack_uses_descriptor_read_for_one_high_confidence_graph(tmp_path: Path) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    toolset = RtgFederationToolset(load_registry(registry_path))

    route_pack = toolset.vellis_route_pack_preview(text="Which component specs lack evidence?")
    route_gate = toolset.vellis_route_pack_gate(text="Which component specs lack evidence?")

    assert route_pack["ok"] is True
    result = route_pack["result"]
    assert [context["graph_id"] for context in result["graph_contexts"]] == ["repo_twin"]
    assert result["selected_skill"]["execution_profile"] == "descriptor_read"
    assert result["selected_skill"]["handoff_chain"] == []
    assert result["required_docs"] == []
    assert result["verification_commands"] == [
        {
            "command": "just graph-check",
            "when": "before executing the descriptor-declared read",
        }
    ]
    assert result["scoped_tools"]["graph_local_mcp_tools_after_selection"] == []

    assert route_gate["ok"] is True
    gate = route_gate["result"]
    assert gate["decision"] == "invoke"
    assert gate["graph_targets"]["graph_context_ids"] == ["repo_twin"]
    assert gate["next_actions"] == [
        {"action": "run_verification_commands", "commands": ["just graph-check"]},
        {
            "action": "execute_descriptor_read",
            "graph_id": "repo_twin",
            "query_name": "repo_components_evidence_status",
            "command": "just graph-query untested",
        },
    ]
    assert gate["freshness_and_evidence"]["stale_recovery_command"] == "just graph-verify"


def test_federation_toolset_preflight_checks_declared_read_runtime(tmp_path: Path) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_federated_preflight()

    assert result["ok"] is True, result
    assert result["result"]["status"] == "passed"
    assert result["result"]["ready_graph_count"] == 1
    assert result["result"]["skipped_graph_count"] == 1
    repo = [graph for graph in result["result"]["graphs"] if graph["graph_id"] == "repo_twin"][0]
    assert repo["status"] == "ready"
    assert repo["citation_projection"] == {
        "status": "ready",
        "query_name": "repo_components_evidence_status",
        "anchor_bucket": "component",
        "error": None,
    }
    assert repo["snapshot"]["status"] == "restored"
    assert repo["validation"]["status"] == "accepted"


def test_federation_toolset_preflight_reports_missing_snapshot(tmp_path: Path) -> None:
    graph_root = tmp_path / "repo-twin"
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_federated_preflight()

    assert result["ok"] is True
    assert result["result"]["status"] == "failed"
    assert result["result"]["not_ready_graph_ids"] == ["repo_twin"]
    repo = [graph for graph in result["result"]["graphs"] if graph["graph_id"] == "repo_twin"][0]
    assert repo["snapshot"]["status"] == "failed"
    assert repo["snapshot"]["error"]["type"] == "RtgControllerSnapshotFailed"
    assert repo["validation"]["status"] == "not_run"


def test_federation_toolset_preflight_rejects_invalid_citation_projection(
    tmp_path: Path,
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["graphs"][0]["metadata"]["citation_projection"]["anchor_bucket"] = "missing"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_federated_preflight()

    assert result["ok"] is True
    assert result["result"]["status"] == "failed"
    repo = [graph for graph in result["result"]["graphs"] if graph["graph_id"] == "repo_twin"][0]
    assert repo["status"] == "not_ready"
    assert repo["citation_projection"]["status"] == "invalid"
    assert "anchor_bucket must be returned" in repo["citation_projection"]["error"]
    assert "descriptor-declared citation projection is not ready" in repo["reasons"]


def test_federation_toolset_surfaces_candidate_hints_without_traversal_permission(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_candidate_catalog(bridge_path)
    toolset = RtgFederationToolset(
        load_registry(registry_path),
        load_bridge_store(bridge_path),
        bridge_path,
    )

    plan = toolset.vellis_federated_plan(text="Compare component evidence with personal decisions.")

    assert plan["ok"] is True
    candidate_hints = plan["result"]["bridge_hints"]["candidate_hints"]
    assert plan["result"]["bridge_hints"]["matching_bridge_count"] == 0
    assert candidate_hints["status"] == "candidate_only"
    assert candidate_hints["matching_candidate_count"] == 1
    assert candidate_hints["traversal_permission"] is False
    assert candidate_hints["candidates"][0]["status"] == "candidate_only"
    assert candidate_hints["candidates"][0]["confidence"] == 0.48
    assert [item["action"] for item in candidate_hints["review_checklist"][0]["items"]] == [
        "review_candidate_evidence",
        "graph_local_read",
        "graph_local_read",
        "promote_or_reject_candidate",
    ]


def test_federation_toolset_returns_structured_federated_answer(
    tmp_path: Path,
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path, graph_root=graph_root)
    write_bridge_catalog(bridge_path)
    toolset = RtgFederationToolset(
        load_registry(registry_path),
        load_bridge_store(bridge_path),
        bridge_path,
    )

    result = toolset.vellis_federated_answer(
        text="Compare component evidence with personal decisions."
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "partial"
    assert result["result"]["read_execution"] == "performed"
    assert result["result"]["join_execution"] == "not_performed"
    synthesis = result["result"]["synthesis"]
    assert synthesis["answer"]["executed_graph_count"] == 1
    assert synthesis["answer"]["planned_graph_count"] == 2
    assert synthesis["answer"]["bridge_count"] == 1
    assert {citation["graph_id"] for citation in synthesis["citations"]} == {"repo_twin"}
    citation_uuids = {citation["local_uuid"] for citation in synthesis["citations"]}
    repo_read = [read for read in synthesis["reads"] if read["graph_id"] == "repo_twin"][0]
    answer_uuids = {
        component["local_uuid"] for component in repo_read["summary"]["answer"]["components"]
    }
    assert citation_uuids == answer_uuids
    assert len(citation_uuids) == 2
    assert all(UUID(value) for value in citation_uuids)
    assert all("local_id" not in citation for citation in synthesis["citations"])
    assert synthesis["limitations"] == (
        (
            "graph personal_ops read was unsupported: "
            "no supported federated canned query for this graph"
        ),
    )


def test_federation_toolset_returns_evidence_bounded_semantic_answer(
    tmp_path: Path,
) -> None:
    class SourceBoundGenerator:
        def generate(
            self,
            request: RtgEvidenceBoundedSynthesisRequest,
        ) -> RtgSemanticSynthesisDraft:
            citation = request.source.citations[0]
            return RtgSemanticSynthesisDraft(
                claims=(
                    RtgSemanticClaimDraft(
                        text="The repo twin reports component evidence status.",
                        kind="summary",
                        citation_refs=(
                            RtgEvidenceCitationRef(
                                graph_id=citation.graph_id,
                                local_uuid=citation.local_uuid,
                            ),
                        ),
                    ),
                )
            )

    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    toolset = RtgFederationToolset(
        load_registry(registry_path),
        semantic_generator=SourceBoundGenerator(),
    )

    result = toolset.vellis_federated_semantic_answer(
        text="Which component specs lack evidence?",
        target_graph_ids=["repo_twin"],
    )

    assert result["ok"] is True
    answer = result["result"]
    assert answer["status"] == "complete"
    assert answer["model_execution"] == "performed"
    assert answer["deterministic_answer"]["status"] == "complete"
    assert answer["semantic_synthesis"]["entailment_status"] == "not_verified"
    assert answer["semantic_synthesis"]["claims"][0]["citations"][0]["graph_id"] == ("repo_twin")
    assert answer["join_execution"] == "not_performed"
    assert answer["write_execution"] == "not_performed"


def test_federation_toolset_requires_explicit_semantic_configuration(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)

    result = RtgFederationToolset(load_registry(registry_path)).vellis_federated_semantic_answer(
        text="Summarize repo evidence."
    )

    assert result["ok"] is False
    assert result["error"] == {
        "type": "RtgGraphRegistryInvalid",
        "message": ("semantic synthesis is not configured; start the server with --semantic-model"),
    }


def test_federation_toolset_resolves_graph_qualified_citation(
    tmp_path: Path,
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    toolset = RtgFederationToolset(load_registry(registry_path))
    answer = toolset.vellis_federated_answer(
        text="Which component specs lack evidence?",
        target_graph_ids=["repo_twin"],
    )
    citation = answer["result"]["synthesis"]["citations"][0]

    resolved = toolset.vellis_resolve_citation(
        graph_id=citation["graph_id"],
        local_uuid=citation["local_uuid"],
    )

    assert resolved["ok"] is True
    result = resolved["result"]
    assert result["status"] == "resolved"
    assert result["graph_id"] == "repo_twin"
    assert result["local_uuid"] == citation["local_uuid"]
    assert result["query_name"] == "repo_components_evidence_status"
    assert result["anchor_bucket"] == "component"
    assert result["records"]
    assert {record["anchors"]["component"] for record in result["records"]} == {
        citation["local_uuid"]
    }
    assert result["provenance"]["graph"] == {
        "graph_id": "repo_twin",
        "authority": "derived_from_repo",
    }
    assert result["provenance"]["snapshot"]["restore"]["status"] == "restored"
    assert result["provenance"]["projection"] == {
        "query_name": "repo_components_evidence_status",
        "anchor_bucket": "component",
    }


def test_federation_toolset_reports_unsupported_and_invalid_citation_resolution(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, include_read_capability=False)
    toolset = RtgFederationToolset(load_registry(registry_path))

    unsupported = toolset.vellis_resolve_citation(
        graph_id="repo_twin",
        local_uuid="11111111-1111-4111-8111-111111111111",
    )
    invalid = toolset.vellis_resolve_citation(
        graph_id="repo_twin",
        local_uuid="component.rtg.query",
    )

    assert unsupported["ok"] is True
    assert unsupported["result"]["status"] == "unsupported"
    assert unsupported["result"]["records"] == ()
    assert invalid["ok"] is False
    assert invalid["error"]["type"] == "RtgCitationResolutionInvalid"


def test_federation_toolset_traverses_one_active_bridge_without_joining(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(personal_attention_overview, "_today", lambda: date(2026, 7, 10))
    repo_root = tmp_path / "repo-twin"
    personal_root = tmp_path / "personal-ops"
    seed_repo_component_snapshot(repo_root, "snapshots/test.json")
    seed_personal_ops_snapshot(personal_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(
        registry_path,
        graph_root=repo_root,
        personal_graph_root=personal_root,
        include_personal_read_capability=True,
    )
    registry = load_registry(registry_path)
    read_toolset = RtgFederationToolset(registry)
    repo_answer = read_toolset.vellis_federated_answer(
        text="Which component specs lack evidence?",
        target_graph_ids=["repo_twin"],
    )
    personal_answer = read_toolset.vellis_federated_answer(
        text="What needs attention this week?",
        target_graph_ids=["personal_ops"],
    )
    repo_citation = repo_answer["result"]["synthesis"]["citations"][0]
    personal_citation = personal_answer["result"]["synthesis"]["citations"][0]
    source = RtgGraphLocalReference(
        graph_id=repo_citation["graph_id"],
        local_uuid=UUID(repo_citation["local_uuid"]),
    )
    target = RtgGraphLocalReference(
        graph_id=personal_citation["graph_id"],
        local_uuid=UUID(personal_citation["local_uuid"]),
    )
    bridge_store = InMemoryRtgGraphBridge.empty()
    bridge = bridge_store.put_bridge(
        RtgGraphBridgeDraft(
            bridge_type="related_context",
            source=source,
            target=target,
            confidence=0.8,
            asserted_at="2026-07-10T00:00:00Z",
            asserted_by="agent.codex",
            provenance=(source,),
        )
    )
    toolset = RtgFederationToolset(registry, bridge_store)

    traversed = toolset.vellis_traverse_bridge(bridge.bridge_id)

    assert traversed["ok"] is True
    result = traversed["result"]
    assert result["status"] == "resolved"
    assert result["bridge"]["bridge_id"] == bridge.bridge_id
    assert result["bridge"]["status"] == "active"
    assert result["source"]["reference"] == {
        "graph_id": source.graph_id,
        "local_uuid": str(source.local_uuid),
    }
    assert result["target"]["reference"] == {
        "graph_id": target.graph_id,
        "local_uuid": str(target.local_uuid),
    }
    assert result["source"]["resolution"]["records"]
    assert result["target"]["resolution"]["records"]
    assert "joined_record" not in result
    assert result["join_execution"] == "not_performed"
    assert bridge_store.get_bridge(bridge.bridge_id) == bridge


def test_federation_toolset_requires_configured_bridge_for_traversal(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_traverse_bridge("bridge_11111111111111111111")

    assert result["ok"] is False
    assert result["error"]["type"] == "RtgGraphRegistryInvalid"
    assert result["error"]["message"] == "bridge catalog is not configured"


def test_federation_toolset_requires_descriptor_capability_for_federated_answer(
    tmp_path: Path,
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(
        registry_path,
        graph_root=graph_root,
        include_read_capability=False,
    )
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_federated_answer(
        text="Which component specs lack evidence?",
        target_graph_ids=["repo_twin"],
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "no_supported_reads"
    synthesis = result["result"]["synthesis"]
    assert synthesis["answer"]["executed_graph_count"] == 0
    assert synthesis["citations"] == ()
    assert synthesis["limitations"] == (
        (
            "graph repo_twin read was unsupported: "
            "no supported federated canned query for this graph"
        ),
    )


def test_federation_toolset_promotes_bridge_candidate_and_refreshes_hints(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_candidate_catalog(bridge_path)
    toolset = RtgFederationToolset(
        load_registry(registry_path),
        load_bridge_store(bridge_path),
        bridge_path,
    )
    listed = toolset.vellis_bridge_candidates()
    candidate_id = listed["result"]["candidates"][0]["candidate_id"]

    promoted = toolset.vellis_promote_bridge_candidate(
        candidate_id=candidate_id,
        asserted_at="2026-07-09T01:00:00Z",
        asserted_by="agent.codex",
    )
    listed_after = toolset.vellis_bridge_candidates(status="all")
    plan_after = toolset.vellis_federated_plan(
        text="Compare component evidence with personal decisions."
    )
    catalog = json.loads(bridge_path.read_text(encoding="utf-8"))

    assert promoted["ok"] is True
    assert promoted["result"]["candidate"]["status"] == "promoted"
    assert promoted["result"]["bridge"]["status"] == "active"
    assert promoted["result"]["bridge"]["metadata"]["promoted_from_candidate_id"] == candidate_id
    assert listed_after["result"]["candidates"][0]["status"] == "promoted"
    assert catalog["candidates"][0]["status"] == "promoted"
    assert (
        catalog["candidates"][0]["promoted_bridge_id"] == promoted["result"]["bridge"]["bridge_id"]
    )
    assert len(catalog["bridges"]) == 1
    assert plan_after["result"]["bridge_hints"]["matching_bridge_count"] == 1
    assert plan_after["result"]["bridge_hints"]["candidate_hints"]["status"] == (
        "suppressed_by_confirmed_bridge"
    )


def test_federation_toolset_rejects_bridge_candidate_without_bridge_assertion(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_candidate_catalog(bridge_path)
    toolset = RtgFederationToolset(
        load_registry(registry_path),
        load_bridge_store(bridge_path),
        bridge_path,
    )
    candidate_id = toolset.vellis_bridge_candidates()["result"]["candidates"][0]["candidate_id"]

    rejected = toolset.vellis_reject_bridge_candidate(
        candidate_id=candidate_id,
        rejected_at="2026-07-09T01:00:00Z",
        rejected_by="agent.codex",
        reason="candidate evidence did not support traversal",
    )
    listed_after = toolset.vellis_bridge_candidates(status="all")
    plan_after = toolset.vellis_federated_plan(
        text="Compare component evidence with personal decisions."
    )
    catalog = json.loads(bridge_path.read_text(encoding="utf-8"))

    assert rejected["ok"] is True
    assert rejected["result"]["candidate"]["status"] == "rejected"
    assert rejected["result"]["candidate"]["rejection_reason"] == (
        "candidate evidence did not support traversal"
    )
    assert listed_after["result"]["candidates"][0]["status"] == "rejected"
    assert catalog["candidates"][0]["status"] == "rejected"
    assert catalog["bridges"] == []
    assert plan_after["result"]["bridge_hints"]["matching_bridge_count"] == 0
    assert plan_after["result"]["bridge_hints"]["candidate_hints"]["status"] == "none"


def test_federation_toolset_route_query_executes_selected_graph_snapshot(
    tmp_path: Path,
) -> None:
    graph_root = tmp_path / "repo-twin"
    _seed_person_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_route_query(
        text="Which component specs lack evidence?",
        query_spec={
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
        target_graph_id="repo_twin",
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "query_executed"
    assert result["result"]["route"]["selected_graph_id"] == "repo_twin"
    assert result["result"]["snapshot_restore"]["status"] == "restored"
    assert result["result"]["query"]["ok"] is True
    assert result["result"]["query"]["result"]["row_count"] == 1
    assert result["result"]["query"]["result"]["rows"][0]["properties"]["profile"]["name"] == "Ada"


def test_federation_toolset_canned_repo_components_evidence_status(
    tmp_path: Path,
) -> None:
    graph_root = tmp_path / "repo-twin"
    seed_repo_component_snapshot(graph_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path, graph_root=graph_root)
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_route_query(
        text="Which component specs lack evidence?",
        canned_query="repo_components_evidence_status",
    )

    assert result["ok"] is True, result
    assert result["result"]["status"] == "query_executed"
    assert result["result"]["route"]["selected_graph_id"] == "repo_twin"
    assert result["result"]["canned_query"]["name"] == "repo_components_evidence_status"
    assert result["result"]["canned_query"]["implementation"] == (
        "apps.rtg_federation.queries.repo_components_evidence_status:CANNED_QUERY"
    )
    assert result["result"]["answer"]["component_count"] == 2
    assert result["result"]["answer"]["missing_evidence_count"] == 1
    assert result["result"]["answer"]["missing_evidence_component_ids"] == [
        "component.without_evidence"
    ]
    with_evidence = [
        component
        for component in result["result"]["answer"]["components"]
        if component["component_id"] == "component.with_evidence"
    ][0]
    assert with_evidence["evidence_count"] == 1
    assert with_evidence["newest_evidence_at"] == "2026-07-09T00:00:00Z"


def test_federation_toolset_canned_personal_attention_overview(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(personal_attention_overview, "_today", lambda: date(2026, 7, 10))
    personal_root = tmp_path / "personal-ops"
    seed_personal_ops_snapshot(personal_root, "snapshots/test.json")
    _make_snapshot_legacy_for_federation_restore(personal_root / "snapshots" / "test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(
        registry_path,
        personal_graph_root=personal_root,
        include_personal_read_capability=True,
    )
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_route_query(
        text="What needs attention this week?",
        canned_query="personal_attention_overview",
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "query_executed"
    assert result["result"]["route"]["selected_graph_id"] == "personal_ops"
    assert result["result"]["snapshot_restore"]["legacy_link_system_stripped_count"] == 1
    assert result["result"]["snapshot_restore"]["compatibility_projection"] == (
        "read_only_current_kernel"
    )
    assert (
        result["result"]["snapshot_restore"][
            "unsupported_schema_time_shape_stripped_count"
        ]
        > 0
    )
    assert (
        result["result"]["snapshot_restore"][
            "unsupported_schema_identity_criteria_stripped_count"
        ]
        > 0
    )
    assert (
        result["result"]["snapshot_restore"][
            "unsupported_schema_link_kind_stripped_count"
        ]
        > 0
    )
    assert result["result"]["snapshot_restore"]["legacy_schema_time_shape_backfilled_count"] == 0
    assert result["result"]["snapshot_restore"]["legacy_schema_link_kind_defaulted_count"] == 0
    assert result["result"]["canned_query"]["name"] == "personal_attention_overview"
    assert result["result"]["answer"]["item_count"] == 5
    assert result["result"]["answer"]["attention_scope"] == "this_week"
    assert result["result"]["answer"]["attention_window"] == {
        "label": "this_week",
        "start": "2026-07-10",
        "end": "2026-07-17",
    }
    assert result["result"]["answer"]["attention_item_count"] == 3
    assert {item["title"] for item in result["result"]["answer"]["attention_items"]} == {
        "Invite first beta testers",
        "Sunday household reset",
        "Jordan",
    }
    assert result["result"]["answer"]["evidence_gap_count"] == 1
    assert result["result"]["answer"]["relationship_open_loop_count"] == 1
    assert result["result"]["answer"]["counts_by_kind"] == {
        "commitment": 1,
        "decision": 1,
        "evidence": 1,
        "relationship_context": 1,
        "routine": 1,
    }


def test_federation_toolset_federated_answer_executes_personal_attention_read(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(personal_attention_overview, "_today", lambda: date(2026, 7, 10))
    personal_root = tmp_path / "personal-ops"
    seed_personal_ops_snapshot(personal_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    write_registry(
        registry_path,
        personal_graph_root=personal_root,
        include_personal_read_capability=True,
    )
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_federated_answer(text="What needs attention this week?")

    assert result["ok"] is True
    assert result["result"]["status"] == "complete"
    synthesis = result["result"]["synthesis"]
    assert synthesis["answer"]["executed_graph_count"] == 1
    assert synthesis["answer"]["planned_graph_count"] == 1
    assert synthesis["reads"][0]["query_name"] == "personal_attention_overview"
    answer = synthesis["reads"][0]["summary"]["answer"]
    assert answer["attention_item_count"] == 3
    assert {citation["graph_id"] for citation in synthesis["citations"]} == {"personal_ops"}
    citation_uuids = {citation["local_uuid"] for citation in synthesis["citations"]}
    answer_uuids = {
        item["local_uuid"]
        for section in ("attention_items", "evidence_gaps")
        for item in answer[section]
    }
    assert citation_uuids == answer_uuids
    assert all(UUID(value) for value in citation_uuids)
    assert all("local_id" not in citation for citation in synthesis["citations"])
    assert synthesis["limitations"] == ()


def test_federation_toolset_route_query_refuses_ambiguous_routes(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_route_query(
        text="Find evidence.",
        query_spec={"anchor_buckets": [{"name": "person", "anchor_type_keys": ["Person"]}]},
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "route_requires_confirmation"
    assert result["result"]["query_executed"] is False
    assert result["result"]["route"]["selected_graph_id"] is None


def test_federation_toolset_returns_registry_errors(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_graph_mcp_info("missing_graph")

    assert result["ok"] is False
    assert result["error"]["type"] == "RtgGraphNotFound"


def test_federation_mcp_dry_run_reports_control_plane_metadata(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    bridge_path = tmp_path / "bridges.json"
    write_registry(registry_path)
    write_bridge_catalog(bridge_path)

    status = mcp_dry_run_status(
        registry_path,
        bridge_path=bridge_path,
        transport="http",
        host="127.0.0.1",
        port=8775,
        path="/mcp",
    )

    assert status["app"]["graph_count"] == 2
    assert status["app"]["bridge_catalog_status"] == "loaded"
    assert status["app"]["bridge_count"] == 1
    assert status["app"]["bridge_candidate_count"] == 1
    assert status["app"]["semantic_synthesis"] == {
        "status": "not_configured",
        "model": None,
        "api_key_env": None,
    }
    assert status["mcp"]["server_name"] == "rtg_federation"
    assert {tool["name"] for tool in status["mcp"]["tools"]} == {
        "vellis_list_graphs",
        "vellis_federated_capabilities",
        "vellis_federated_preflight",
        "vellis_intent_compile",
        "vellis_route_pack_preview",
        "vellis_route_pack_gate",
        "vellis_federated_plan",
        "vellis_federated_answer",
        "vellis_federated_semantic_answer",
        "vellis_resolve_citation",
        "vellis_traverse_bridge",
        "vellis_graph_mcp_info",
        "vellis_route_query",
        "vellis_bridge_candidates",
        "vellis_bridge_candidate",
        "vellis_promote_bridge_candidate",
        "vellis_reject_bridge_candidate",
    }
    assert status["mcp"]["client_config"]["mcpServers"]["rtg_federation"]["url"] == (
        "http://127.0.0.1:8775/mcp"
    )


def test_federation_mcp_dry_run_reports_semantic_opt_in(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)

    status = mcp_dry_run_status(
        registry_path,
        semantic_model="gpt-5.6-luna",
        semantic_api_key_env="VELLIS_OPENAI_KEY",
    )

    assert status["app"]["semantic_synthesis"] == {
        "status": "enabled_requested",
        "model": "gpt-5.6-luna",
        "api_key_env": "VELLIS_OPENAI_KEY",
    }
    launch_args = status["mcp"]["launch"]["args"]
    assert launch_args[-4:] == [
        "--semantic-model",
        "gpt-5.6-luna",
        "--semantic-api-key-env",
        "VELLIS_OPENAI_KEY",
    ]


def test_federation_cli_dry_run_prints_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    registry_path = tmp_path / "registry.json"
    write_registry(registry_path)

    exit_code = main(
        [
            "serve-mcp",
            "--registry",
            str(registry_path),
            "--transport",
            "http",
            "--dry-run",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["app"]["graph_count"] == 2
    assert output["mcp"]["server_name"] == "rtg_federation"


def test_federation_mcp_stdio_protocol_lists_and_routes(tmp_path: Path) -> None:
    async def run_protocol_check() -> None:
        repo_root = Path(__file__).resolve().parents[3]
        registry_path = tmp_path / "registry.json"
        bridge_path = tmp_path / "bridges.json"
        graph_root = tmp_path / "repo-twin"
        seed_repo_component_snapshot(graph_root, "snapshots/test.json")
        write_registry(registry_path, graph_root=graph_root)
        write_bridge_catalog(bridge_path)
        params = StdioServerParameters(
            command="uv",
            args=[
                "--directory",
                str(repo_root),
                "run",
                "python",
                "-m",
                "apps.rtg_federation",
                "serve-mcp",
                "--transport",
                "stdio",
                "--registry",
                str(registry_path),
                "--bridges",
                str(bridge_path),
            ],
            cwd=tmp_path,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                listed = await session.call_tool("vellis_list_graphs", {})
                capabilities = await session.call_tool("vellis_federated_capabilities", {})
                preflight = await session.call_tool("vellis_federated_preflight", {})
                routed = await session.call_tool(
                    "vellis_intent_compile",
                    {"text": "Which component specs lack evidence?"},
                )
                route_pack = await session.call_tool(
                    "vellis_route_pack_preview",
                    {"text": "Compare component evidence with personal decisions."},
                )
                route_gate = await session.call_tool(
                    "vellis_route_pack_gate",
                    {"text": "Compare component evidence with personal decisions."},
                )
                planned = await session.call_tool(
                    "vellis_federated_plan",
                    {"text": "Compare component evidence with personal decisions."},
                )
                planned_during_session = _tool_result_payload(planned)
                bridge_id = planned_during_session["result"]["bridge_hints"]["bridges"][0][
                    "bridge_id"
                ]
                traversed = await session.call_tool(
                    "vellis_traverse_bridge",
                    {"bridge_id": bridge_id},
                )
                answered = await session.call_tool(
                    "vellis_federated_answer",
                    {"text": "Compare component evidence with personal decisions."},
                )
                answered_during_session = _tool_result_payload(answered)
                citation = answered_during_session["result"]["synthesis"]["citations"][0]
                resolved = await session.call_tool(
                    "vellis_resolve_citation",
                    {
                        "graph_id": citation["graph_id"],
                        "local_uuid": citation["local_uuid"],
                    },
                )
                mcp_info = await session.call_tool(
                    "vellis_graph_mcp_info",
                    {"graph_id": "repo_twin"},
                )
                canned = await session.call_tool(
                    "vellis_route_query",
                    {
                        "text": "Which component specs lack evidence?",
                        "canned_query": "repo_components_evidence_status",
                    },
                )
                bridge_candidates = await session.call_tool(
                    "vellis_bridge_candidates",
                    {"status": "candidate_only"},
                )

        listed_payload = _tool_result_payload(listed)
        capabilities_payload = _tool_result_payload(capabilities)
        preflight_payload = _tool_result_payload(preflight)
        routed_payload = _tool_result_payload(routed)
        route_pack_payload = _tool_result_payload(route_pack)
        route_gate_payload = _tool_result_payload(route_gate)
        planned_payload = _tool_result_payload(planned)
        traversed_payload = _tool_result_payload(traversed)
        answered_payload = _tool_result_payload(answered)
        resolved_payload = _tool_result_payload(resolved)
        mcp_info_payload = _tool_result_payload(mcp_info)
        canned_payload = _tool_result_payload(canned)
        bridge_candidates_payload = _tool_result_payload(bridge_candidates)

        assert tool_names == {
            "vellis_list_graphs",
            "vellis_federated_capabilities",
            "vellis_federated_preflight",
            "vellis_intent_compile",
            "vellis_route_pack_preview",
            "vellis_route_pack_gate",
            "vellis_federated_plan",
            "vellis_federated_answer",
            "vellis_federated_semantic_answer",
            "vellis_resolve_citation",
            "vellis_traverse_bridge",
            "vellis_graph_mcp_info",
            "vellis_route_query",
            "vellis_bridge_candidates",
            "vellis_bridge_candidate",
            "vellis_promote_bridge_candidate",
            "vellis_reject_bridge_candidate",
        }
        assert listed_payload["ok"] is True
        assert capabilities_payload["result"]["ready_capability_count"] == 1
        assert preflight_payload["result"]["status"] == "passed"
        assert routed_payload["result"]["selected_graph_id"] == "repo_twin"
        assert route_pack_payload["result"]["selected_skill"]["name"] == (
            "rtg-federation-control-plane"
        )
        route_pack_graph_ids = [
            context["graph_id"] for context in route_pack_payload["result"]["graph_contexts"]
        ]
        assert route_pack_graph_ids == [
            "personal_ops",
            "repo_twin",
        ]
        assert route_pack_payload["result"]["freshness_and_evidence"]["preflight"]["status"] == (
            "passed"
        )
        assert route_gate_payload["result"]["decision"] == "clarify"
        assert route_gate_payload["result"]["graph_targets"]["selected_graph_id"] == (
            "personal_ops"
        )
        assert "missing_mcp_endpoint" in route_gate_payload["result"]["clarification_hazard_codes"]
        assert (
            "vellis_route_pack_gate"
            in route_gate_payload["result"]["allowed_tools"]["federation_mcp_tools"]
        )
        assert planned_payload["result"]["executable"] is True
        assert [step["graph_id"] for step in planned_payload["result"]["steps"]] == [
            "personal_ops",
            "repo_twin",
        ]
        assert planned_payload["result"]["bridge_hints"]["matching_bridge_count"] == 1
        assert traversed_payload["result"]["status"] == "unresolved"
        assert traversed_payload["result"]["join_execution"] == "not_performed"
        assert answered_payload["result"]["status"] == "partial"
        assert answered_payload["result"]["synthesis"]["answer"]["executed_graph_count"] == 1
        assert resolved_payload["result"]["status"] == "resolved"
        assert resolved_payload["result"]["records"]
        checklist = planned_payload["result"]["bridge_hints"]["follow_up_checklist"][0]
        assert [item["action"] for item in checklist["items"]] == [
            "graph_local_read",
            "graph_local_read",
            "synthesize_outside_graph",
        ]
        assert (
            mcp_info_payload["result"]["client_config"]["mcpServers"]["vellis_repo_twin"]["url"]
            == "http://127.0.0.1:8765/mcp"
        )
        assert canned_payload["result"]["answer"]["missing_evidence_component_ids"] == [
            "component.without_evidence"
        ]
        assert bridge_candidates_payload["result"]["candidate_count"] == 1

    asyncio.run(run_protocol_check())


def _seed_person_snapshot(graph_root: Path, snapshot_path: str) -> None:
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="Person.",
            payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
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
        )
    )
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        schema,
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(graph_root),
        SqliteStorage.open(graph_root / "controller.sqlite"),
    )
    toolset = RtgMcpToolset(controller)
    applied = toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "ada"},
                "type": "Person",
                "display_name": "Ada",
                "facts": [
                    {
                        "type": "Profile",
                        "properties": {"name": "Ada"},
                    }
                ],
            }
        ]
    )
    persisted = toolset.rtg_persist_system_snapshot(snapshot_path, return_snapshot=False)
    assert applied["ok"] is True
    assert persisted["ok"] is True


def _make_snapshot_legacy_for_federation_restore(snapshot_path: Path) -> None:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    for link in payload["graph"]["links"]:
        link["system"] = {"live": True}
    for definition in payload["schema"]["definitions"]:
        if definition["kind"] in {"anchor", "data_object"}:
            definition["time_shape"] = "state_now"
            definition["identity_criteria"] = []
        if definition["kind"] == "link":
            definition["payload"]["link_kind"] = "semantic"
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")


def _tool_result_payload(result: object) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return cast(dict[str, Any], structured)
    content = cast(Any, result).content
    text = content[0].text
    return cast(dict[str, Any], json.loads(text))
