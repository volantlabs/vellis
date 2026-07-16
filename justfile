set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

setup:
    @uv sync --dev

test:
    @if find apps components tests -path '*/test_*.py' -print -quit 2>/dev/null | grep -q .; then uv run pytest -m "not integration"; else echo "No tests found."; fi

test-integration:
    @if find apps components tests -path '*/test_*.py' -print -quit 2>/dev/null | grep -q .; then uv run pytest -m integration; else echo "No tests found."; fi

test-full:
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

package-check:
    @rm -rf dist
    @uv build
    @uv run python tools/package_check.py

# Fetch and verify pinned SysML/KerML assets, then inspect the validator gate.
model-setup:
    @uv run python tools/model_tool.py setup

model-check-foundation:
    @uv run python tools/model_tool.py check --scope foundation

model-check-bibliotek:
    @uv run python tools/model_tool.py check --scope bibliotek

model-check-vellis:
    @uv run python tools/model_tool.py check --scope vellis

# Run repository profile, architecture, realization, and generated-artifact checks.
model-check:
    @uv run python tools/model_tool.py package
    @uv run python tools/model_tool.py check --scope all --require-external
    @uv run python tools/sysml_diagrams.py check --backend pilot
    @uv run python tools/model_views.py architecture check
    @uv run python tools/model_tool.py check-generated
    @uv run python tools/sysml_reference.py check

model-check-formal:
    @uv run python tools/model_tool.py package
    @uv run python tools/sysml_validator.py validate-products --self-test

model-diagrams:
    @uv run python tools/sysml_validator.py export-index --output generated/model/formal-model-index.json
    @uv run python tools/sysml_diagrams.py render --backend pilot

model-render:
    @uv run python tools/sysml_validator.py export-index --output generated/model/formal-model-index.json
    @uv run python tools/sysml_diagrams.py render --backend pilot
    @uv run python tools/model_views.py architecture render
    @uv run python tools/model_tool.py render

# Regenerate only the parser-backed architecture graph and stable dashboard.
model-dashboard:
    @uv run python tools/sysml_validator.py export-index --output generated/model/formal-model-index.json
    @uv run python tools/model_views.py architecture render

# Discover and render ephemeral architecture projections under build/model-views/.
model-view-presets:
    @uv run python tools/model_views.py presets

model-view-targets *args:
    @uv run python tools/model_views.py targets {{args}}

model-view *args:
    @uv run python tools/model_views.py render {{args}}

model-view-changed BASE="main":
    @uv run python tools/model_views.py changed --base "{{BASE}}"

model-view-promote *args:
    @uv run python tools/model_views.py promote {{args}}

model-reference-render:
    @uv run python tools/sysml_reference.py render

model-reference-check:
    @uv run python tools/sysml_reference.py check

model-reference-find query:
    @uv run python tools/sysml_reference.py find "{{query}}"

model-package:
    @uv run python tools/model_tool.py package

model-diff:
    @uv run python tools/model_tool.py diff

model-handoff *args:
    @target="{{args}}"; target="${target#TARGET=}"; test -n "$target" || { echo "Set TARGET=<stable-id>" >&2; exit 2; }; uv run python tools/model_tool.py handoff "$target"

# Generate a read-only advisory model/implementation evidence bundle.
model-audit target="":
    @target="{{target}}"; if test -n "$target"; then uv run python tools/model_tool.py audit "$target"; else uv run python tools/model_tool.py audit; fi

# Run the RTG Knowledge Graph app with default .data storage.
rtg:
    @uv run python -m apps.rtg_knowledge_graph --json

# Print default stdio MCP client config, prompt paths, and first-call smoke check.
rtg-mcp-info:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport stdio --dry-run --json

# Print only copy-pastable stdio MCP client configuration.
rtg-mcp-config data_root=".data/rtg_knowledge_graph":
    @uv run vellis-rtg-knowledge-graph mcp-config --transport stdio --storage-root {{data_root}}/json_file --runtime-database-path {{data_root}}/runtime.sqlite

# Launch the default RTG Knowledge Graph stdio MCP server.
rtg-mcp:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport stdio

# Print localhost HTTP MCP client config for one explicit local data root.
rtg-mcp-http-info data_root=".data/rtg_knowledge_graph" host="127.0.0.1" port="8765" path="/mcp":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --dry-run --json --storage-root {{data_root}}/json_file --runtime-database-path {{data_root}}/runtime.sqlite

# Launch an unauthenticated localhost HTTP MCP server.
rtg-mcp-http data_root=".data/rtg_knowledge_graph" host="127.0.0.1" port="8765" path="/mcp":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --storage-root {{data_root}}/json_file --runtime-database-path {{data_root}}/runtime.sqlite

# Print eval MCP metadata with an isolated explicit data root.
rtg-eval-info data_root=".data/vellis-runtime-eval-001":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport stdio --dry-run --json --storage-root {{data_root}}/json_file --runtime-database-path {{data_root}}/runtime.sqlite --empty --manual-recovery

run-rtg-knowledge-graph *args:
    @uv run python -m apps.rtg_knowledge_graph {{args}}

run-rtg-knowledge-graph-mcp *args:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp {{args}}

run-rtg-knowledge-graph-mcp-info *args:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --dry-run --json {{args}}

check: lint typecheck skills-check model-check test package-check
