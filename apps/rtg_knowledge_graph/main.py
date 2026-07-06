from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_launch import (
    DEFAULT_LOCALHOST_HOST,
    DEFAULT_LOCALHOST_PATH,
    DEFAULT_LOCALHOST_PORT,
)
from apps.rtg_knowledge_graph.mcp_server import mcp_dry_run_status, run_mcp_server


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rtg_knowledge_graph")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("serve-mcp",),
        default="run",
        help="Optional command. Omit for the normal app smoke run.",
    )
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=None,
        help="Local directory root for JSON File Storage.",
    )
    parser.add_argument(
        "--sql-database-path",
        type=Path,
        default=None,
        help="SQLite database path for the controller ledger.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON status.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="MCP transport for serve-mcp. Use http for unauthenticated localhost MCP.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_LOCALHOST_HOST,
        help="Host to bind for --transport http. Defaults to localhost.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_LOCALHOST_PORT,
        help="Port to bind for --transport http.",
    )
    parser.add_argument(
        "--path",
        default=DEFAULT_LOCALHOST_PATH,
        help="MCP endpoint path for --transport http.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Initialize the app and report MCP metadata without starting the server.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.storage_root is not None:
        config = RtgKnowledgeGraphConfig(
            storage_root=args.storage_root,
            sql_database_path=args.sql_database_path or args.storage_root / "controller.sqlite",
        )
    else:
        env_config = RtgKnowledgeGraphConfig.from_env()
        config = (
            RtgKnowledgeGraphConfig(
                storage_root=env_config.storage_root,
                sql_database_path=args.sql_database_path,
            )
            if args.sql_database_path is not None
            else env_config
        )
    if args.command == "serve-mcp":
        if args.dry_run:
            status = mcp_dry_run_status(
                config,
                transport=args.transport,
                host=args.host,
                port=args.port,
                path=args.path,
            )
            if args.json:
                print(json.dumps(status, sort_keys=True))
            else:
                tools = status["mcp"]["tools"]
                endpoint = (
                    ""
                    if args.transport == "stdio"
                    else f", url={status['mcp']['transports']['localhost_http']['url']}"
                )
                print(
                    "rtg_knowledge_graph MCP: "
                    f"{len(tools)} tool(s), "
                    f"transport={status['mcp']['transport']}, "
                    f"storage_root={status['app']['storage_root']}"
                    f"{endpoint}"
                )
            return 0
        run_mcp_server(
            config,
            transport=args.transport,
            host=args.host,
            port=args.port,
            path=args.path,
        )
        return 0

    composition = build_app(config)
    status = composition.runner.run()

    if args.json:
        print(json.dumps(status.to_json_value(), sort_keys=True))
    else:
        print(
            f"{status.app_name}: "
            f"{status.json_document_count} JSON document(s), "
            f"manifest={status.manifest_path}, "
            f"storage_root={status.storage_root}"
        )

    return 0
