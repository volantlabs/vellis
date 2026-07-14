set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

setup:
    @uv sync --dev

test:
    @if find apps components tests tools -path '*/test_*.py' -print -quit 2>/dev/null | grep -q .; then uv run pytest; else echo "No tests found."; fi

lint:
    @uv run ruff check .

format:
    @uv run ruff format .

skills-check:
    @uv run python tools/validate_skills.py
    @uv run python tools/sync_agent_skills.py --check

skills-sync:
    @uv run python tools/sync_agent_skills.py

graph-sync storage_root=".data/repo-twin":
    @uv run python -m tools.repo_twin sync --storage-root {{storage_root}}

graph-check storage_root=".data/repo-twin":
    @uv run python -m tools.repo_twin check --storage-root {{storage_root}}

graph-report storage_root=".data/repo-twin" format="markdown":
    @uv run python -m tools.repo_twin report --storage-root {{storage_root}} --format {{format}}

graph-query name *args:
    @uv run python -m tools.repo_twin query {{name}} {{args}}

rtg-graphs registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} list

rtg-route query operation="read" registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} route --operation {{operation}} "{{query}}"

rtg-route-pack-preview query operation="read" registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} route-pack-preview --operation {{operation}} "{{query}}"

rtg-route-pack-gate query operation="read" registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} route-pack-gate --operation {{operation}} "{{query}}"

rtg-federated-plan query operation="read" registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} federated-plan --operation {{operation}} "{{query}}"

rtg-federated-capabilities registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} federated-capabilities

rtg-federated-capabilities-check registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} federated-capabilities --check

rtg-federation-preflight registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} federated-preflight --check

rtg-federated-capability-template query_name:
    @uv run python -m tools.rtg_graph_registry federated-capability-template {{query_name}}

rtg-federated-answer query operation="read" registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} federated-answer --operation {{operation}} "{{query}}"

rtg-citation-resolve graph_id local_uuid registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} resolve-citation {{graph_id}} {{local_uuid}}

rtg-bridge-traverse bridge_id registry="docs/rtg-monographs/registry.json" bridges="docs/rtg-monographs/bridges.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} bridge-traverse --bridges {{bridges}} {{bridge_id}}

rtg-route-query query canned_query="repo_components_evidence_status" registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} route-query --canned-query {{canned_query}} "{{query}}"

rtg-bridge-candidates status="candidate_only" registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} bridge-candidates list --status {{status}}

rtg-bridge-candidate candidate_id registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} bridge-candidates inspect {{candidate_id}}

rtg-bridge-candidate-promote candidate_id asserted_at asserted_by registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} bridge-candidates promote {{candidate_id}} --asserted-at {{asserted_at}} --asserted-by {{asserted_by}}

rtg-bridge-candidate-reject candidate_id rejected_at rejected_by reason registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} bridge-candidates reject {{candidate_id}} --rejected-at {{rejected_at}} --rejected-by {{rejected_by}} --reason "{{reason}}"

rtg-monograph-mcp-info graph_id registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} mcp-info {{graph_id}}

rtg-monograph-init graph_id registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} init {{graph_id}}

rtg-monograph-mcp graph_id registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_graph_registry --registry {{registry}} serve-http {{graph_id}}

rtg-federation-mcp-info registry="docs/rtg-monographs/registry.json" host="127.0.0.1" port="8775" path="/mcp":
    @uv run python -m apps.rtg_federation serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --registry {{registry}} --dry-run --json

rtg-federation-mcp registry="docs/rtg-monographs/registry.json" host="127.0.0.1" port="8775" path="/mcp":
    @uv run python -m apps.rtg_federation serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --registry {{registry}}

rtg-federation-mcp-semantic model registry="docs/rtg-monographs/registry.json" host="127.0.0.1" port="8775" path="/mcp":
    @uv run python -m apps.rtg_federation serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --registry {{registry}} --semantic-model {{model}}

rtg-federation-eval cases="docs/guides/vellis/evals/rtg-federation-routing-cases.json" registry="docs/rtg-monographs/registry.json":
    @uv run python -m tools.rtg_federation_eval --registry {{registry}} --cases {{cases}}

rtg-federation-workload-eval cases="docs/guides/vellis/evals/rtg-federation-workload-cases.json" registry="docs/rtg-monographs/registry.json" bridges="docs/rtg-monographs/bridges.json":
    @uv run python -m tools.rtg_federation_workload_eval --registry {{registry}} --bridges {{bridges}} --cases {{cases}}

graph-evidence kind *command:
    @uv run python -m tools.repo_twin evidence {{kind}} -- {{command}}

# Run tests through the evidence wrapper so ordinary checks refresh model/realization evidence.
test-evidence:
    @uv run python -m tools.repo_twin evidence test_run -- just test

graph-verify storage_root=".data/repo-twin":
    @uv run python -m tools.repo_twin sync --storage-root {{storage_root}}
    @uv run python -m tools.repo_twin check --storage-root {{storage_root}}

typecheck:
    @uv run basedpyright

build:
    @uv build

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
    @uv run python tools/model_tool.py check-generated
    @uv run python tools/sysml_reference.py check

model-check-formal:
    @uv run python tools/model_tool.py package
    @uv run python tools/sysml_validator.py validate-products --self-test

model-render:
    @uv run python tools/sysml_validator.py export-index --output generated/model/formal-model-index.json
    @uv run python tools/model_tool.py render

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
rtg-mcp-config storage_root=".data/vellis-beta-001":
    @uv run vellis-rtg-knowledge-graph mcp-config --transport stdio --storage-root {{storage_root}}

# Launch the default RTG Knowledge Graph stdio MCP server.
rtg-mcp:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport stdio

# Print localhost HTTP MCP client config for a fresh beta storage root.
rtg-mcp-http-info storage_root=".data/vellis-beta-001" host="127.0.0.1" port="8765" path="/mcp":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --dry-run --json --storage-root {{storage_root}}

# Launch an unauthenticated localhost HTTP MCP server.
rtg-mcp-http storage_root=".data/vellis-beta-001" host="127.0.0.1" port="8765" path="/mcp":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport http --host {{host}} --port {{port}} --path {{path}} --storage-root {{storage_root}} --sql-database-path {{storage_root}}/controller.sqlite

# Print beta eval MCP metadata with an explicit storage root.
rtg-eval-info storage_root=".data/vellis-beta-001":
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --transport stdio --dry-run --json --storage-root {{storage_root}} --empty --manual-recovery

run-rtg-knowledge-graph *args:
    @uv run python -m apps.rtg_knowledge_graph {{args}}

run-rtg-knowledge-graph-mcp *args:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp {{args}}

run-rtg-knowledge-graph-mcp-info *args:
    @uv run python -m apps.rtg_knowledge_graph serve-mcp --dry-run --json {{args}}

# Launch the Personal Launcher local web UI.
launcher-dev host="127.0.0.1" port="18777":
    @uv run python -m apps.personal_launcher --host {{host}} --port {{port}} --open-browser

# Install or refresh the macOS desktop application wrapper.
launcher-app destination="":
    @if [ -n "{{destination}}" ]; then uv run python -m apps.personal_launcher install-desktop-app --desktop-app-path "{{destination}}"; else uv run python -m apps.personal_launcher install-desktop-app; fi

check: lint typecheck skills-check model-check test-evidence graph-verify
