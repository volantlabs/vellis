from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig

MCP_SERVER_NAME = "rtg_knowledge_graph"
MCP_STATE_MODE = "fresh_single_session"
DEFAULT_LOCALHOST_HOST = "127.0.0.1"
DEFAULT_LOCALHOST_PORT = 8765
DEFAULT_LOCALHOST_PATH = "/mcp"
RECOMMENDED_EVAL_PROMPT_ID = "individual_life_graph"
EVAL_PROMPTS = {
    "individual_life_graph": {
        "title": "RTG Individual Life Graph Beta Prompt",
        "path": "docs/evals/rtg-individual-life-graph-beta-prompt.md",
        "description": ("Initial single-user personal and professional life-graph beta scenario."),
    },
    "component_repo_affordance": {
        "title": "RTG Agent Affordance Eval Prompt",
        "path": "docs/evals/rtg-agent-affordance-eval-prompt.md",
        "description": "Software-component repository modeling scenario.",
    },
}
GUIDES = {
    "known_good_walkthrough": {
        "title": "RTG Beta Known-Good Walkthrough",
        "path": "docs/evals/rtg-beta-known-good-walkthrough.md",
        "description": "Expected shape of a successful first life-graph beta run.",
    }
}
FIRST_CALL = {
    "tool": "rtg_validate_graph",
    "arguments": {},
    "expected": {
        "ok": True,
        "result.accepted": True,
        "result.findings": [],
    },
    "purpose": "Confirm the MCP client is connected to a fresh, valid RTG controller.",
}


def repository_root() -> Path | None:
    return _find_repository_root(Path(__file__).resolve())


def eval_prompt_path() -> Path | None:
    return eval_prompt_paths()[RECOMMENDED_EVAL_PROMPT_ID]


def eval_prompt_paths() -> dict[str, Path | None]:
    repo_root = repository_root()
    if repo_root is None:
        return {prompt_id: None for prompt_id in EVAL_PROMPTS}
    return {
        prompt_id: _existing_prompt_path(repo_root, str(prompt["path"]))
        for prompt_id, prompt in EVAL_PROMPTS.items()
    }


def guide_paths() -> dict[str, Path | None]:
    repo_root = repository_root()
    if repo_root is None:
        return {guide_id: None for guide_id in GUIDES}
    return {
        guide_id: _existing_prompt_path(repo_root, str(guide["path"]))
        for guide_id, guide in GUIDES.items()
    }


def mcp_launch_metadata(
    config: RtgKnowledgeGraphConfig,
    *,
    localhost_host: str = DEFAULT_LOCALHOST_HOST,
    localhost_port: int = DEFAULT_LOCALHOST_PORT,
    localhost_path: str = DEFAULT_LOCALHOST_PATH,
    preferred_transport: str = "stdio",
) -> dict[str, Any]:
    repo_root = repository_root()
    storage_root = _absolute(config.storage_root)
    sql_database_path = _absolute(config.sql_database_path)
    if repo_root is not None:
        launch_args = [
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
            str(storage_root),
            "--sql-database-path",
            str(sql_database_path),
        ]
        launch = {
            "command": "uv",
            "args": launch_args,
            "cwd": str(repo_root),
        }
        launch_mode = "repository_checkout"
    else:
        launch_args = [
            "-m",
            "apps.rtg_knowledge_graph",
            "serve-mcp",
            "--transport",
            "stdio",
            "--storage-root",
            str(storage_root),
            "--sql-database-path",
            str(sql_database_path),
        ]
        launch = {
            "command": sys.executable,
            "args": launch_args,
        }
        launch_mode = "installed_package"
    prompt_paths = eval_prompt_paths()
    paths_by_guide = guide_paths()
    localhost_launch = _localhost_launch(
        repo_root=repo_root,
        storage_root=storage_root,
        sql_database_path=sql_database_path,
        host=localhost_host,
        port=localhost_port,
        path=localhost_path,
    )
    localhost_url = _localhost_url(localhost_host, localhost_port, localhost_path)
    transports = {
        "stdio": {
            "launch": launch,
            "client_config": {
                "mcpServers": {
                    MCP_SERVER_NAME: {
                        **launch,
                    }
                }
            },
        },
        "localhost_http": {
            "url": localhost_url,
            "transport": "http",
            "host": localhost_host,
            "port": localhost_port,
            "path": localhost_path,
            "auth": "none",
            "network_scope": "localhost",
            "launch": localhost_launch,
            "client_config": {
                "mcpServers": {
                    MCP_SERVER_NAME: {
                        "url": localhost_url,
                        "transport": "http",
                    }
                }
            },
        },
    }
    selected_transport = "localhost_http" if preferred_transport == "http" else "stdio"
    return {
        "launch_mode": launch_mode,
        "state_mode": MCP_STATE_MODE,
        "eval_prompt_path": _optional_path_text(eval_prompt_path()),
        "recommended_eval_prompt": RECOMMENDED_EVAL_PROMPT_ID,
        "eval_prompts": {
            prompt_id: {
                **prompt,
                "path": _optional_path_text(prompt_paths[prompt_id]),
                "available": prompt_paths[prompt_id] is not None,
                "recommended": prompt_id == RECOMMENDED_EVAL_PROMPT_ID,
            }
            for prompt_id, prompt in EVAL_PROMPTS.items()
        },
        "guides": {
            guide_id: {
                **guide,
                "path": _optional_path_text(paths_by_guide[guide_id]),
                "available": paths_by_guide[guide_id] is not None,
            }
            for guide_id, guide in GUIDES.items()
        },
        "first_call": FIRST_CALL,
        "transports": transports,
        "launch": transports[selected_transport]["launch"],
        "client_config": transports[selected_transport]["client_config"],
    }


def _localhost_launch(
    *,
    repo_root: Path | None,
    storage_root: Path,
    sql_database_path: Path,
    host: str,
    port: int,
    path: str,
) -> dict[str, Any]:
    if repo_root is not None:
        return {
            "command": "uv",
            "args": [
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
                host,
                "--port",
                str(port),
                "--path",
                path,
                "--storage-root",
                str(storage_root),
                "--sql-database-path",
                str(sql_database_path),
            ],
            "cwd": str(repo_root),
        }
    return {
        "command": sys.executable,
        "args": [
            "-m",
            "apps.rtg_knowledge_graph",
            "serve-mcp",
            "--transport",
            "http",
            "--host",
            host,
            "--port",
            str(port),
            "--path",
            path,
            "--storage-root",
            str(storage_root),
            "--sql-database-path",
            str(sql_database_path),
        ],
    }


def _localhost_url(host: str, port: int, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"http://{host}:{port}{normalized_path}"


def _absolute(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _find_repository_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "apps" / "rtg_knowledge_graph").is_dir()
            and (candidate / "docs" / "evals").is_dir()
        ):
            return candidate
    return None


def _existing_prompt_path(repo_root: Path, relative_path: str) -> Path | None:
    path = repo_root / relative_path
    return path if path.is_file() else None


def _optional_path_text(path: Path | None) -> str | None:
    return None if path is None else str(path)
