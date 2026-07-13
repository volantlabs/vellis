from __future__ import annotations

import argparse
import io
import json
import os
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_launch import (
    DEFAULT_LOCALHOST_HOST,
    DEFAULT_LOCALHOST_PATH,
    DEFAULT_LOCALHOST_PORT,
    mcp_launch_metadata,
    repository_root,
)
from apps.rtg_knowledge_graph.mcp_server import mcp_dry_run_status, run_mcp_server
from apps.rtg_knowledge_graph.onboarding import (
    CLIENTS,
    config_for_data_dir,
    doctor_report,
    setup_vellis,
)
from apps.rtg_knowledge_graph.starter_schema import VellisStartupFailed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="vellis",
        description="Set up, check, or run the local Vellis knowledge graph.",
        epilog=(
            "First run:\n"
            "  vellis setup\n\n"
            "The MCP client owns the configured stdio process; do not start a second one."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("setup", "doctor", "serve-mcp", "mcp-config"),
        default="run",
        help=(
            "Optional command. Use setup for the ordinary first-run experience; "
            "omit for the normal app smoke run."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Vellis data directory (defaults to .data/rtg_knowledge_graph).",
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
        "--client",
        choices=("auto", *CLIENTS),
        default="auto",
        help=(
            "MCP client for setup or doctor. For mcp-config, codex prints an exact command; "
            "all other values print generic JSON."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept the one setup confirmation after human authorization.",
    )
    parser.add_argument(
        "--empty",
        action="store_true",
        help="Developer/evaluation mode: do not install the starter schema.",
    )
    parser.add_argument(
        "--manual-recovery",
        action="store_true",
        help="Developer/evaluation mode: do not replay durable state automatically.",
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
    if args.data_dir is not None and (
        args.storage_root is not None or args.sql_database_path is not None
    ):
        raise SystemExit("--data-dir cannot be combined with --storage-root/--sql-database-path")
    if args.data_dir is not None:
        config = config_for_data_dir(
            args.data_dir,
            install_starter_schema=not args.empty,
            automatic_recovery=not args.manual_recovery,
        )
    elif args.storage_root is not None:
        config = RtgKnowledgeGraphConfig(
            storage_root=args.storage_root,
            sql_database_path=args.sql_database_path or args.storage_root / "controller.sqlite",
            install_starter_schema=not args.empty,
            automatic_recovery=not args.manual_recovery,
        )
    else:
        env_config = RtgKnowledgeGraphConfig.from_env(cwd=repository_root() or Path.cwd())
        config = (
            RtgKnowledgeGraphConfig(
                storage_root=env_config.storage_root,
                sql_database_path=args.sql_database_path,
                install_starter_schema=not args.empty,
                automatic_recovery=not args.manual_recovery,
            )
            if args.sql_database_path is not None
            else RtgKnowledgeGraphConfig(
                storage_root=env_config.storage_root,
                sql_database_path=env_config.sql_database_path,
                install_starter_schema=not args.empty,
                automatic_recovery=not args.manual_recovery,
            )
        )
    try:
        return _run_command(args, config)
    except VellisStartupFailed as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        else:
            print(f"Vellis setup failed: {error}", file=sys.stderr)
        return 1


def _run_command(args: argparse.Namespace, config: RtgKnowledgeGraphConfig) -> int:
    if args.command == "setup":
        result = setup_vellis(
            config,
            client=args.client,
            yes=args.yes,
            output_stream=io.StringIO() if args.json else None,
        )
        if args.json:
            print(json.dumps(result.to_json_value(), sort_keys=True))
        else:
            if result.client == "generic-json":
                print(
                    f"\nAdd the complete MCP configuration at {result.registration} to your client."
                )
            print("\nVellis is ready. Restart or reload your MCP client, then say:\n")
            print(f'  "{result.first_prompt}"')
        return 0

    if args.command == "doctor":
        report = doctor_report(config, client=args.client)
        if args.json:
            print(json.dumps(report, sort_keys=True))
        else:
            for check in report["checks"]:
                marker = "OK" if check["ok"] else "FAIL"
                print(f"[{marker}] {check['id']}: {check['detail']}")
        return 0 if report["ok"] else 1

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
        try:
            run_mcp_server(
                config,
                transport=args.transport,
                host=args.host,
                port=args.port,
                path=args.path,
            )
        except KeyboardInterrupt:
            # FastMCP completes its transport shutdown before propagating the interrupt.
            # Treat that expected operator action as a clean CLI exit.
            pass
        return 0

    if args.command == "mcp-config":
        metadata = mcp_launch_metadata(
            config,
            localhost_host=args.host,
            localhost_port=args.port,
            localhost_path=args.path,
            preferred_transport=args.transport,
        )
        client_config = metadata["client_config"]
        if args.client == "codex":
            print(_codex_mcp_add_command(client_config))
        else:
            print(json.dumps(client_config, indent=2, sort_keys=True))
        return 0

    composition = build_app(config)
    composition.prepare()
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


def _codex_mcp_add_command(client_config: object) -> str:
    if not isinstance(client_config, dict):
        raise ValueError("MCP client configuration must be an object")
    servers = client_config.get("mcpServers")
    if not isinstance(servers, dict) or len(servers) != 1:
        raise ValueError("MCP client configuration must contain exactly one server")
    server_name, raw_server = next(iter(servers.items()))
    if not isinstance(server_name, str) or not isinstance(raw_server, dict):
        raise ValueError("MCP server configuration is invalid")

    url = raw_server.get("url")
    if isinstance(url, str):
        command = ["codex", "mcp", "add", server_name, "--url", url]
    else:
        executable = raw_server.get("command")
        args = raw_server.get("args")
        if (
            not isinstance(executable, str)
            or not isinstance(args, list)
            or not all(isinstance(value, str) for value in args)
        ):
            raise ValueError("stdio MCP server configuration has an invalid command or arguments")
        command = ["codex", "mcp", "add", server_name, "--", executable, *args]

    if os.name == "nt":
        return " ".join(_powershell_quote(value) for value in command)
    return shlex.join(command)


def _powershell_quote(value: str) -> str:
    if value and all(character.isalnum() or character in "-._/:\\" for character in value):
        return value
    return "'" + value.replace("'", "''") + "'"
