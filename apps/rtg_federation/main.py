from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from apps.rtg_federation.mcp_server import (
    DEFAULT_LOCALHOST_HOST,
    DEFAULT_LOCALHOST_PATH,
    DEFAULT_LOCALHOST_PORT,
    mcp_dry_run_status,
    run_mcp_server,
)
from apps.rtg_federation.registry_io import DEFAULT_REGISTRY_PATH


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rtg_federation")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("serve-mcp",),
        default="serve-mcp",
        help="Command to run. Defaults to serve-mcp.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help="Path to an RTG monograph registry JSON file.",
    )
    parser.add_argument(
        "--bridges",
        type=Path,
        default=None,
        help="Path to an optional RTG bridge assertion catalog JSON file.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="MCP transport. Use http for unauthenticated localhost MCP.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_LOCALHOST_HOST,
        help="Host to bind for --transport http.",
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
        help="Report MCP metadata without starting the server.",
    )
    parser.add_argument(
        "--semantic-model",
        default=None,
        help=(
            "Explicitly enable evidence-bounded OpenAI semantic synthesis with this model. "
            "The deterministic federation tools remain model-free."
        ),
    )
    parser.add_argument(
        "--semantic-api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable containing the OpenAI API key when --semantic-model is set.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        status = mcp_dry_run_status(
            args.registry,
            bridge_path=args.bridges,
            transport=args.transport,
            host=args.host,
            port=args.port,
            path=args.path,
            semantic_model=args.semantic_model,
            semantic_api_key_env=args.semantic_api_key_env,
        )
        if args.json:
            print(json.dumps(status, sort_keys=True))
        else:
            print(
                "rtg_federation MCP: "
                f"{len(status['mcp']['tools'])} tool(s), "
                f"transport={status['mcp']['transport']}, "
                f"registry={status['app']['registry_path']}"
            )
        return 0
    run_mcp_server(
        args.registry,
        bridge_path=args.bridges,
        transport=args.transport,
        host=args.host,
        port=args.port,
        path=args.path,
        semantic_model=args.semantic_model,
        semantic_api_key_env=args.semantic_api_key_env,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
