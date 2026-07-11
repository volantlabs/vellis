from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from apps.rtg_knowledge_graph import mcp_launch
from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import (
    DEFAULT_SQL_DATABASE_PATH,
    DEFAULT_STORAGE_ROOT,
    SQL_DATABASE_PATH_ENV_VAR,
    STORAGE_ROOT_ENV_VAR,
    RtgKnowledgeGraphConfig,
)


def test_config_uses_default_storage_root_relative_to_cwd(tmp_path: Path) -> None:
    config = RtgKnowledgeGraphConfig.from_env(env={}, cwd=tmp_path)

    assert config.storage_root == tmp_path / DEFAULT_STORAGE_ROOT
    assert config.sql_database_path == tmp_path / DEFAULT_SQL_DATABASE_PATH


def test_config_uses_env_storage_root(tmp_path: Path) -> None:
    configured = tmp_path / "configured-storage"
    config = RtgKnowledgeGraphConfig.from_env(
        env={
            STORAGE_ROOT_ENV_VAR: str(configured),
            SQL_DATABASE_PATH_ENV_VAR: str(tmp_path / "configured.sqlite"),
        },
        cwd=tmp_path / "ignored",
    )

    assert config.storage_root == configured
    assert config.sql_database_path == tmp_path / "configured.sqlite"


def test_composed_app_runs_and_writes_manifest(tmp_path: Path) -> None:
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        sql_database_path=tmp_path / "controller.sqlite",
    )
    composition = build_app(config)

    status = composition.runner.run()

    assert status.app_name == "rtg_knowledge_graph"
    assert status.manifest_path == "system/app_manifest.json"
    assert status.json_document_count == 1
    assert status.rtg_controller_ready is True

    manifest_path = config.storage_root / status.manifest_path
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)

    dependency_ids = {item["id"] for item in manifest["component_dependencies"]}
    assert dependency_ids == {
        "component.storage.json_file",
        "component.storage.sql",
        "component.rtg.controller",
        "component.rtg.graph",
        "component.rtg.schema",
        "component.rtg.constraints",
        "component.rtg.migration",
        "component.rtg.change_validation",
        "component.rtg.query",
    }
    assert manifest["interfaces"] == [
        {
            "kind": "mcp",
            "server_name": "rtg_knowledge_graph",
            "transport": "stdio",
            "launch_mode": "repository_checkout",
            "state_mode": "fresh_single_session",
            "eval_prompt_path": str(
                Path("docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md").resolve()
            ),
            "recommended_eval_prompt": "individual_life_graph",
            "eval_prompts": {
                "individual_life_graph": {
                    "title": "RTG Individual Life Graph Beta Prompt",
                    "path": str(
                        Path("docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md").resolve()
                    ),
                    "description": (
                        "Initial single-user personal and professional life-graph beta scenario."
                    ),
                    "available": True,
                    "recommended": True,
                },
                "component_repo_affordance": {
                    "title": "RTG Agent Affordance Eval Prompt",
                    "path": str(
                        Path(
                            "docs/guides/vellis/evals/rtg-agent-affordance-eval-prompt.md"
                        ).resolve()
                    ),
                    "description": "Software-component repository modeling scenario.",
                    "available": True,
                    "recommended": False,
                },
            },
            "guides": {
                "known_good_walkthrough": {
                    "title": "RTG Beta Known-Good Walkthrough",
                    "path": str(
                        Path(
                            "docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md"
                        ).resolve()
                    ),
                    "description": "Expected shape of a successful first life-graph beta run.",
                    "available": True,
                },
            },
            "first_call": {
                "tool": "rtg_validate_graph",
                "arguments": {},
                "expected": {
                    "ok": True,
                    "result.accepted": True,
                    "result.findings": [],
                },
                "purpose": "Confirm the MCP client is connected to a fresh, valid RTG controller.",
            },
            "transports": {
                "stdio": {
                    "launch": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            str(Path(".").resolve()),
                            "run",
                            "python",
                            "-m",
                            "apps.rtg_knowledge_graph",
                            "serve-mcp",
                            "--transport",
                            "stdio",
                            "--storage-root",
                            str((tmp_path / "storage").resolve()),
                            "--sql-database-path",
                            str((tmp_path / "controller.sqlite").resolve()),
                        ],
                        "cwd": str(Path(".").resolve()),
                    },
                    "client_config": {
                        "mcpServers": {
                            "rtg_knowledge_graph": {
                                "command": "uv",
                                "args": [
                                    "--directory",
                                    str(Path(".").resolve()),
                                    "run",
                                    "python",
                                    "-m",
                                    "apps.rtg_knowledge_graph",
                                    "serve-mcp",
                                    "--transport",
                                    "stdio",
                                    "--storage-root",
                                    str((tmp_path / "storage").resolve()),
                                    "--sql-database-path",
                                    str((tmp_path / "controller.sqlite").resolve()),
                                ],
                                "cwd": str(Path(".").resolve()),
                            }
                        }
                    },
                },
                "localhost_http": {
                    "url": "http://127.0.0.1:8765/mcp",
                    "transport": "http",
                    "host": "127.0.0.1",
                    "port": 8765,
                    "path": "/mcp",
                    "auth": "none",
                    "network_scope": "localhost",
                    "launch": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            str(Path(".").resolve()),
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
                            "8765",
                            "--path",
                            "/mcp",
                            "--storage-root",
                            str((tmp_path / "storage").resolve()),
                            "--sql-database-path",
                            str((tmp_path / "controller.sqlite").resolve()),
                        ],
                        "cwd": str(Path(".").resolve()),
                    },
                    "client_config": {
                        "mcpServers": {
                            "rtg_knowledge_graph": {
                                "url": "http://127.0.0.1:8765/mcp",
                                "transport": "http",
                            }
                        }
                    },
                },
            },
            "launch": {
                "command": "uv",
                "args": [
                    "--directory",
                    str(Path(".").resolve()),
                    "run",
                    "python",
                    "-m",
                    "apps.rtg_knowledge_graph",
                    "serve-mcp",
                    "--transport",
                    "stdio",
                    "--storage-root",
                    str((tmp_path / "storage").resolve()),
                    "--sql-database-path",
                    str((tmp_path / "controller.sqlite").resolve()),
                ],
                "cwd": str(Path(".").resolve()),
            },
            "client_config": {
                "mcpServers": {
                    "rtg_knowledge_graph": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            str(Path(".").resolve()),
                            "run",
                            "python",
                            "-m",
                            "apps.rtg_knowledge_graph",
                            "serve-mcp",
                            "--transport",
                            "stdio",
                            "--storage-root",
                            str((tmp_path / "storage").resolve()),
                            "--sql-database-path",
                            str((tmp_path / "controller.sqlite").resolve()),
                        ],
                        "cwd": str(Path(".").resolve()),
                    }
                }
            },
        }
    ]


def test_cli_runs_full_app(tmp_path: Path) -> None:
    storage_root = tmp_path / "cli-storage"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "--storage-root",
            str(storage_root),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    status = json.loads(result.stdout)
    assert status["app_name"] == "rtg_knowledge_graph"
    assert status["manifest_path"] == "system/app_manifest.json"
    assert status["json_document_count"] == 1
    assert status["rtg_controller_ready"] is True
    assert (storage_root / "system" / "app_manifest.json").exists()
    assert (storage_root / "controller.sqlite").exists()


def test_cli_reports_mcp_dry_run_metadata(tmp_path: Path) -> None:
    storage_root = tmp_path / "mcp-storage"
    sql_database_path = tmp_path / "mcp-ledger.sqlite"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "serve-mcp",
            "--storage-root",
            str(storage_root),
            "--sql-database-path",
            str(sql_database_path),
            "--dry-run",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    status = json.loads(result.stdout)
    tool_names = {item["name"] for item in status["mcp"]["tools"]}
    launch = status["mcp"]["launch"]
    client_config = status["mcp"]["client_config"]["mcpServers"]["rtg_knowledge_graph"]
    localhost_http = status["mcp"]["transports"]["localhost_http"]

    assert status["mcp"]["transport"] == "stdio"
    assert status["mcp"]["launch_mode"] == "repository_checkout"
    assert status["mcp"]["state_mode"] == "fresh_single_session"
    assert status["mcp"]["eval_prompt_path"].endswith(
        "docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md"
    )
    assert status["mcp"]["recommended_eval_prompt"] == "individual_life_graph"
    assert set(status["mcp"]["eval_prompts"]) == {
        "individual_life_graph",
        "component_repo_affordance",
    }
    assert status["mcp"]["eval_prompts"]["individual_life_graph"]["recommended"] is True
    assert status["mcp"]["eval_prompts"]["individual_life_graph"]["available"] is True
    assert status["mcp"]["eval_prompts"]["component_repo_affordance"]["recommended"] is False
    assert status["mcp"]["guides"]["known_good_walkthrough"]["available"] is True
    assert status["mcp"]["guides"]["known_good_walkthrough"]["path"].endswith(
        "docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md"
    )
    assert set(status["mcp"]["guides"]) == {"known_good_walkthrough"}
    assert status["mcp"]["first_call"] == {
        "tool": "rtg_validate_graph",
        "arguments": {},
        "expected": {
            "ok": True,
            "result.accepted": True,
            "result.findings": [],
        },
        "purpose": "Confirm the MCP client is connected to a fresh, valid RTG controller.",
    }
    assert len(tool_names) == 27
    assert "rtg_apply_live_graph_changes" in tool_names
    assert "rtg_validate_live_graph_changes" in tool_names
    assert "rtg_apply_live_anchor_records" in tool_names
    assert "rtg_validate_live_anchor_records" in tool_names
    assert "rtg_resolve_anchor_by_fact" in tool_names
    assert "rtg_get_agent_affordance_eval_prompt" not in tool_names
    assert launch["command"] == "uv"
    assert launch["args"][:2] == ["--directory", str(Path(".").resolve())]
    assert "--storage-root" in launch["args"]
    assert "--sql-database-path" in launch["args"]
    assert str(sql_database_path.resolve()) in launch["args"]
    assert client_config == launch
    assert localhost_http["url"] == "http://127.0.0.1:8765/mcp"
    assert localhost_http["client_config"]["mcpServers"]["rtg_knowledge_graph"] == {
        "url": "http://127.0.0.1:8765/mcp",
        "transport": "http",
    }
    assert "--transport" in localhost_http["launch"]["args"]
    assert "http" in localhost_http["launch"]["args"]
    assert (storage_root / "system" / "app_manifest.json").exists()
    assert sql_database_path.exists()


def test_cli_reports_custom_http_mcp_dry_run_metadata(tmp_path: Path) -> None:
    storage_root = tmp_path / "mcp-storage"

    result = subprocess.run(
        [
            "uv",
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
            "9876",
            "--path",
            "/custom-mcp",
            "--storage-root",
            str(storage_root),
            "--dry-run",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    status = json.loads(result.stdout)

    assert status["mcp"]["transport"] == "http"
    assert status["mcp"]["client_config"] == {
        "mcpServers": {
            "rtg_knowledge_graph": {
                "url": "http://127.0.0.1:9876/custom-mcp",
                "transport": "http",
            }
        }
    }
    assert status["mcp"]["transports"]["localhost_http"]["url"] == (
        "http://127.0.0.1:9876/custom-mcp"
    )
    assert status["mcp"]["transports"]["localhost_http"]["client_config"] == {
        "mcpServers": {
            "rtg_knowledge_graph": {
                "url": "http://127.0.0.1:9876/custom-mcp",
                "transport": "http",
            }
        }
    }


def test_mcp_launch_metadata_has_installed_package_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_launch, "repository_root", lambda: None)
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        sql_database_path=tmp_path / "controller.sqlite",
    )

    metadata = mcp_launch.mcp_launch_metadata(config)
    launch = metadata["launch"]

    assert metadata["launch_mode"] == "installed_package"
    assert metadata["eval_prompt_path"] is None
    assert all(not prompt["available"] for prompt in metadata["eval_prompts"].values())
    assert all(not guide["available"] for guide in metadata["guides"].values())
    assert launch["command"]
    assert launch["args"][:3] == ["-m", "apps.rtg_knowledge_graph", "serve-mcp"]
    assert "cwd" not in launch
    assert metadata["client_config"]["mcpServers"]["rtg_knowledge_graph"] == launch
    assert metadata["transports"]["localhost_http"]["launch"]["args"][:3] == [
        "-m",
        "apps.rtg_knowledge_graph",
        "serve-mcp",
    ]
    assert metadata["transports"]["localhost_http"]["url"] == "http://127.0.0.1:8765/mcp"
