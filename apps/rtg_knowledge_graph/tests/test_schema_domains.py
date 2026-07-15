from __future__ import annotations

from pathlib import Path

import yaml

from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_launch import mcp_launch_metadata, repository_root
from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset
from apps.rtg_knowledge_graph.schema_domains import SCHEMA_DOMAINS
from components.rtg.change_validation import DeterministicRtgChangeValidator
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import InProcessRtgController
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.migration import InMemoryRtgMigration
from components.rtg.query import SimpleRtgQueryEngine
from components.rtg.schema import InMemoryRtgSchema
from components.storage.json_file import LocalJsonFileStorage
from components.storage.sql import SqliteStorage


def _empty_toolset(tmp_path: Path) -> RtgMcpToolset:
    return RtgMcpToolset(
        InProcessRtgController.open(
            InMemoryRtgGraph.empty(),
            InMemoryRtgSchema.empty(),
            InMemoryRtgConstraints.empty(),
            InMemoryRtgMigration.empty(),
            DeterministicRtgChangeValidator(),
            SimpleRtgQueryEngine(),
            LocalJsonFileStorage.open(tmp_path / "json"),
            SqliteStorage.open(tmp_path / "controller.sqlite"),
        )
    )


def test_schema_domain_catalog_paths_and_usage_guide_are_aligned(tmp_path: Path) -> None:
    root = repository_root()
    assert root is not None
    for domain in SCHEMA_DOMAINS.values():
        catalog_path = root / str(domain["catalog_path"])
        assert catalog_path.is_file()
        assert (root / str(domain["prompt_path"])).is_file()
        assert (root / str(domain["walkthrough_path"])).is_file()
        descriptor = yaml.safe_load(catalog_path.read_text())
        assert descriptor["runtime_compatibility"] == {
            "status": domain["runtime_status"],
            "requirements": domain["runtime_requirements"],
            "blockers": domain["runtime_blockers"],
        }

    guide = _empty_toolset(tmp_path).rtg_get_usage_guide("schema_domains")

    assert guide["ok"] is True
    assert [domain["domain_id"] for domain in guide["result"]["domains"]] == list(
        SCHEMA_DOMAINS
    )
    assert {
        domain["domain_id"]
        for domain in guide["result"]["domains"]
        if domain["runtime_status"] == "ready"
    } == {
        "governance_core",
        "agent_memory_spine",
        "individual_life_graph",
        "personal_operating_graph",
        "experience_studio",
        "gothic_ambient_archive",
        "time_room_history",
    }
    assert guide["result"]["guardrails"][0].startswith("Do not auto-install")


def test_mcp_launch_metadata_exposes_available_schema_domains(tmp_path: Path) -> None:
    metadata = mcp_launch_metadata(
        RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "storage",
            sql_database_path=tmp_path / "controller.sqlite",
        )
    )

    assert set(metadata["schema_domains"]) == set(SCHEMA_DOMAINS)
    assert all(domain["available"] for domain in metadata["schema_domains"].values())
    assert {
        domain_id
        for domain_id, domain in metadata["schema_domains"].items()
        if domain["runtime_ready"]
    } == {
        "governance_core",
        "agent_memory_spine",
        "individual_life_graph",
        "personal_operating_graph",
        "experience_studio",
        "gothic_ambient_archive",
        "time_room_history",
    }
