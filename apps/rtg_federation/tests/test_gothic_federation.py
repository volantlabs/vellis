from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from apps.rtg_federation.registry_io import load_registry
from apps.rtg_federation.tests.support import (
    seed_gothic_archive_snapshot,
    seed_personal_ops_snapshot,
    seed_repo_component_snapshot,
)
from apps.rtg_federation.toolset import RtgFederationToolset


def test_federated_answer_executes_gothic_source_index(tmp_path: Path) -> None:
    gothic_root = tmp_path / "gothic-archive"
    seed_gothic_archive_snapshot(gothic_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path, gothic_root=gothic_root)
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_federated_answer(
        text=(
            "Show Gothic archive works, sources, passages, reading trails, and verification gaps."
        )
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "complete"
    synthesis = result["result"]["synthesis"]
    assert synthesis["answer"]["executed_graph_count"] == 1
    assert synthesis["reads"][0]["graph_id"] == "gothic_archive"
    assert synthesis["reads"][0]["query_name"] == "gothic_source_index"
    answer = synthesis["reads"][0]["summary"]["answer"]
    assert answer["item_count"] == 4
    assert answer["counts_by_kind"] == {
        "work": 1,
        "source": 1,
        "passage": 1,
        "reading_trail": 1,
    }
    assert answer["verification_gap_count"] == 2
    assert {item["title"] for item in answer["verification_gaps"]} == {
        "Dracula",
        "Lucy transformation source span",
    }
    assert {citation["graph_id"] for citation in synthesis["citations"]} == {
        "gothic_archive"
    }
    citation_uuids = {citation["local_uuid"] for citation in synthesis["citations"]}
    answer_uuids = {
        item["local_uuid"]
        for section in ("works", "sources", "passages", "reading_trails")
        for item in answer[section]
    }
    assert citation_uuids == answer_uuids
    assert all(UUID(value) for value in citation_uuids)
    assert all("local_id" not in citation for citation in synthesis["citations"])
    assert synthesis["limitations"] == ()


def test_federated_answer_executes_three_graph_reads(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo-twin"
    personal_root = tmp_path / "personal-ops"
    gothic_root = tmp_path / "gothic-archive"
    seed_repo_component_snapshot(repo_root, "snapshots/test.json")
    seed_personal_ops_snapshot(personal_root, "snapshots/test.json")
    seed_gothic_archive_snapshot(gothic_root, "snapshots/test.json")
    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        repo_root=repo_root,
        personal_root=personal_root,
        gothic_root=gothic_root,
    )
    toolset = RtgFederationToolset(load_registry(registry_path))

    result = toolset.vellis_federated_answer(
        text=(
            "Compare repository component evidence gaps, personal commitments needing attention "
            "this week, and Gothic archive works, sources, passages, and reading trails."
        )
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "complete"
    synthesis = result["result"]["synthesis"]
    assert synthesis["answer"]["executed_graph_count"] == 3
    assert synthesis["answer"]["planned_graph_count"] == 3
    assert {read["query_name"] for read in synthesis["reads"]} == {
        "gothic_source_index",
        "personal_attention_overview",
        "repo_components_evidence_status",
    }
    assert {citation["graph_id"] for citation in synthesis["citations"]} == {
        "gothic_archive",
        "personal_ops",
        "repo_twin",
    }
    assert all(UUID(citation["local_uuid"]) for citation in synthesis["citations"])
    assert all("local_id" not in citation for citation in synthesis["citations"])
    assert synthesis["limitations"] == ()


def _write_registry(
    path: Path,
    *,
    repo_root: Path | None = None,
    personal_root: Path | None = None,
    gothic_root: Path | None = None,
) -> None:
    repo_root = repo_root or path.parent / "unused-repo-twin"
    personal_root = personal_root or path.parent / "unused-personal-ops"
    gothic_root = gothic_root or path.parent / "unused-gothic-archive"
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
                        "metadata": {
                            "snapshot_path": "snapshots/test.json",
                            "federated_read_capabilities": [
                                {
                                    "query_name": "repo_components_evidence_status",
                                    "implementation": (
                                        "apps.rtg_federation.queries."
                                        "repo_components_evidence_status:CANNED_QUERY"
                                    ),
                                    "terms": ["component", "evidence", "repo"],
                                }
                            ],
                        },
                    },
                    {
                        "graph_id": "personal_ops",
                        "title": "Personal Operating Graph",
                        "storage_root": str(personal_root),
                        "sql_database_path": str(personal_root / "controller.sqlite"),
                        "authority": "user_authored",
                        "write_policy": "explicit_target_required",
                        "domains": ["commitments", "attention", "evidence"],
                        "tags": ["personal", "this week"],
                        "metadata": {
                            "snapshot_path": "snapshots/test.json",
                            "federated_read_capabilities": [
                                {
                                    "query_name": "personal_attention_overview",
                                    "implementation": (
                                        "apps.rtg_federation.queries."
                                        "personal_attention_overview:CANNED_QUERY"
                                    ),
                                    "terms": ["personal", "commitments", "attention", "this week"],
                                }
                            ],
                        },
                    },
                    {
                        "graph_id": "gothic_archive",
                        "title": "Gothic Ambient Archive",
                        "storage_root": str(gothic_root),
                        "sql_database_path": str(gothic_root / "controller.sqlite"),
                        "authority": "curated_public_domain",
                        "write_policy": "explicit_target_required",
                        "domains": ["literature", "sources", "passages", "reading_trails"],
                        "tags": ["gothic", "public-domain", "docent"],
                        "metadata": {
                            "snapshot_path": "snapshots/test.json",
                            "federated_read_capabilities": [
                                {
                                    "query_name": "gothic_source_index",
                                    "implementation": (
                                        "apps.rtg_federation.queries.gothic_source_index:"
                                        "CANNED_QUERY"
                                    ),
                                    "terms": [
                                        "gothic",
                                        "archive",
                                        "works",
                                        "sources",
                                        "passages",
                                        "reading trails",
                                        "verification gaps",
                                    ],
                                }
                            ],
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
