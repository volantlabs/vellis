set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

setup:
    @uv sync --dev

test:
    @if find apps components tests -path '*/test_*.py' -print -quit 2>/dev/null | grep -q .; then uv run pytest; else echo "No tests found."; fi

lint:
    @uv run ruff check .

format:
    @uv run ruff format .

skills-check:
    @uv run python tools/validate_skills.py
    @uv run python tools/sync_agent_skills.py --check

skills-sync:
    @uv run python tools/sync_agent_skills.py

typecheck:
    @uv run basedpyright

build:
    @uv build

# Run the RTG Knowledge Graph app with default .data storage.
rtg:
    @uv run python -m apps.rtg_knowledge_graph --json

# Print default stdio MCP client config, prompt paths, and first-call smoke check.
rtg-mcp-info:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport stdio --dry-run --json

# Launch the default RTG Knowledge Graph stdio MCP server.
rtg-mcp:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport stdio

# Print localhost HTTP MCP client config for a fresh beta storage root.
rtg-mcp-http-info storage_root="/tmp/vellis-beta-001" host="127.0.0.1" port="8765" path="/mcp":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --dry-run --json --storage-root {{storage_root}}

# Launch an unauthenticated localhost HTTP MCP server.
rtg-mcp-http storage_root="/tmp/vellis-beta-001" host="127.0.0.1" port="8765" path="/mcp":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --storage-root {{storage_root}} --sql-database-path {{storage_root}}/controller.sqlite

# Print beta eval MCP metadata with an explicit storage root.
rtg-eval-info storage_root="/tmp/vellis-beta-001":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport stdio --dry-run --json --storage-root {{storage_root}}

run-rtg-knowledge-graph *args:
    @uv run python -m apps.rtg_knowledge_graph {{args}}

run-rtg-knowledge-graph-mcp *args:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp {{args}}

run-rtg-knowledge-graph-mcp-info *args:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --dry-run --json {{args}}

check: lint typecheck skills-check test
