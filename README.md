# Vellis

This repository contains two deliberately separate products while early adopters benefit from a
single clone:

- **Bibliotek** is the reusable AI-native software component library.
- **Vellis** is the first application composed from Bibliotek: a local RTG (Reified Typed Graph)
  knowledge system for humans working with AI agents, or for agents working on their own.

The repository is clone-and-run for beta and open-source evaluation. It gives first-time users two
entry points:

- **Use Vellis**: run the RTG Knowledge Graph application through MCP (Model Context Protocol) 
  as a full-service knowledge substrate with schema, data CRUD (Create, Read, Update, Delete),
  query, validation, migration, audit, snapshots, restore, adjust, replay, plus agent-facing state 
  summaries and usage guides.
- **Build with the components**: use the storage, RTG graph, schema, migration, validation, query,
  and controller components as reusable building blocks for follow-on applications.

The library and application are independently modeled and packageable even though their Python
sources currently share this repository. Bibliotek never depends on Vellis. In a future repository
layout, each can move to its own repo without changing the component contracts.

## Start Here: Use Vellis With An AI Agent

Install prerequisites, clone the repo, and enter the checkout:

```sh
# macOS
brew install uv just

# or without Homebrew
# install uv directly
curl -LsSf https://astral.sh/uv/install.sh | sh
# for just install options, see: https://just.systems/man/en/packages.html

git clone https://github.com/volantlabs/vellis.git
cd vellis
just setup
```

Create a fresh beta storage root and print copy-pastable MCP client configuration:

```sh
just rtg-eval-info /tmp/vellis-beta-001
```

Copy the generated `mcp.client_config` into your MCP client, start the server using `just rtg`,
then make the first tool call:

```json
{"tool": "rtg_validate_graph", "arguments": {}}
```

A fresh server should return `ok: true`, `result.accepted: true`, and no findings. Then give your
agent a state check:

```json
{"tool": "rtg_get_system_state", "arguments": {}}
```

The state response tells an MCP-only agent whether to bootstrap schema, reuse live schema, inspect
staged work, or replay the ledger. 

Then, give the agent the default life-graph beta prompt:
```text
docs/evals/rtg-individual-life-graph-beta-prompt.md
```

That scenario bootstraps an initial personal/professional schema, writes live graph facts, exercises
bad-write recovery, validates a failed schema evolution, persists a snapshot, and verifies ledger
replay. The detailed runbook is in
[`docs/evals/rtg-agent-affordance-eval-runbook.md`](docs/evals/rtg-agent-affordance-eval-runbook.md).
The known-good walkthrough is
[`docs/evals/rtg-beta-known-good-walkthrough.md`](docs/evals/rtg-beta-known-good-walkthrough.md).
Agents without repository access can fetch generic bootstrap, schema-staging, live-write, lookup,
query, recovery, and audit examples through `rtg_get_usage_guide`; those examples teach payload
shape and tool sequence rather than solving the beta scenario.

The turnkey RTG MCP surface is:

- agent guidance and state: `rtg_get_system_state` with `recommended_workflows`, and
  `rtg_get_usage_guide` topics such as `workflow_patterns` and `request_patterns`
- data CRUD and dry-run validation: `rtg_apply_live_graph_changes`,
  `rtg_validate_live_graph_changes`, plus `rtg_apply_live_anchor_records` and
  `rtg_validate_live_anchor_records` for repeated anchor-with-facts ingestion
- schema and data evolution: `rtg_stage_schema_migration`, `rtg_stage_knowledge_changes`,
  `rtg_apply_migration_cutover`, and `rtg_abandon_migration`
- query and discovery: `rtg_resolve_anchor_by_fact`, `rtg_execute_query` with compact
  `properties_only` responses, `rtg_discover_anchor_types`, and `rtg_get_schema_pack`
- audit and recovery: transaction IDs, ledger positions, compact snapshot persist/list/load,
  restore, replay-window metadata, replay verification, and migration history

For agents that need to attach to an already-running local Vellis app, start the unauthenticated
localhost MCP server instead:

```sh
just rtg-mcp-http /tmp/vellis-beta-001 127.0.0.1 8765 /mcp
```

Then configure the other local agent with the URL client config from `just rtg-mcp-http-info`, or
connect directly to `http://127.0.0.1:8765/mcp`. Keep this mode bound to `127.0.0.1`; it is
intended for same-machine agents and does not add authentication.

## Design Values

Vellis favors modular, reusable components with narrow scope and explicit invariant ownership.

Good components are:

- focused on one coherent responsibility
- reusable outside a single application, transport, runtime, or storage choice
- clear about owned state, public contracts, dependencies, and non-responsibilities
- low-coupling, using public contracts instead of private internals
- simple and elegant, with one clear representation per operation
- verifiable at the boundary with contract, side-effect, and dependency checks

These values keep systems easier to understand, maintain, test, and extend as the component library grows.

The longer-term engineering-system thesis is captured in [`docs/agentic-mbse-engineering-system.md`](docs/agentic-mbse-engineering-system.md): use agents to help humans design and manage a durable MBSE-style model that connects product intent, component architecture, implementation, validation evidence, and task flow.

## Current Focus

Vellis evolves in this order:

1. Build a coherent component library.
2. Ship Vellis as the first turnkey application assembled from those components.
3. Add tooling and SDK surfaces for building software from component models.
4. Add runtime support, including distributed-runtime patterns, when component contracts justify it.

Current generated component views include:

- [`component.storage.json_file`](docs/model/generated/components/component.storage.json_file.md): local filesystem-backed JSON document storage.
- [`component.storage.sql`](docs/model/generated/components/component.storage.sql.md): SQLite-backed generic SQL execution surface for durable relational storage consumers.
- [`component.rtg.graph`](docs/model/generated/components/component.rtg.graph.md): schema-neutral in-memory reified type graph for anchors, data objects, links, and direct UUID indexes.
- [`component.rtg.schema`](docs/model/generated/components/component.rtg.schema.md): RTG-native schema-definition store for live and non-live anchor, data object, and link definitions.
- [`component.rtg.constraints`](docs/model/generated/components/component.rtg.constraints.md): constraint-definition store for RTG graph-pattern and lifecycle rules.
- [`component.rtg.migration`](docs/model/generated/components/component.rtg.migration.md): migration records that track schema, constraint, and graph lifecycle cutover sets.
- [`component.rtg.change_validation`](docs/model/generated/components/component.rtg.change_validation.md): batch validator with isolated validation tracks.
- [`component.rtg.query`](docs/model/generated/components/component.rtg.query.md): declarative graph query evaluator.
- [`component.rtg.discovery`](docs/model/generated/components/component.rtg.discovery.md): draft curated discovery-view component.
- [`component.rtg.controller`](docs/model/generated/components/component.rtg.controller.md): cross-component orchestration and invariant owner.

Current Python implementations include:

- [`components/storage/json_file`](components/storage/json_file/): JSON File Storage protocol, implementation, reference composition, and boundary tests.
- [`components/storage/sql`](components/storage/sql/): SQLite-backed SQL Storage protocol, implementation, reference composition, and boundary tests.
- [`components/rtg/graph`](components/rtg/graph/): in-memory RTG protocol, implementation, reference composition, and boundary tests.
- [`components/rtg/schema`](components/rtg/schema/): in-memory RTG schema registry implementation and boundary tests.
- [`components/rtg/constraints`](components/rtg/constraints/): in-memory RTG constraint registry implementation and boundary tests.
- [`components/rtg/migration`](components/rtg/migration/): in-memory RTG migration-record store implementation and boundary tests.
- [`components/rtg/query`](components/rtg/query/): stateless RTG query engine implementation and boundary tests.
- [`components/rtg/change_validation`](components/rtg/change_validation/): deterministic no-mutation RTG change validator implementation and boundary tests.
- [`components/rtg/controller`](components/rtg/controller/): in-process RTG controller implementation with validation, snapshots, cutover, and SQL-backed ledger behavior.

The first application is:

- [`apps/rtg_knowledge_graph`](apps/rtg_knowledge_graph/): the Vellis RTG Knowledge Graph app. It
  wires JSON File Storage, SQL Storage, and the in-process RTG controller, then exposes the
  controller through local MCP transports for human/agent knowledge-system workflows.

The RTG Knowledge Graph MCP server uses standalone FastMCP v3 from the `fastmcp` package.

Manual evaluation prompts include:

- [`docs/evals/rtg-beta-known-good-walkthrough.md`](docs/evals/rtg-beta-known-good-walkthrough.md): a compact known-good walkthrough for the default life-graph beta path.
- [`docs/evals/rtg-agent-affordance-eval-prompt.md`](docs/evals/rtg-agent-affordance-eval-prompt.md): a copy-pastable agent eval for using RTG as an evolving memory, knowledge graph, and database.
- [`docs/evals/rtg-agent-affordance-eval-runbook.md`](docs/evals/rtg-agent-affordance-eval-runbook.md): launch and prompt-sequencing guidance for running the RTG MCP eval.
- [`docs/evals/rtg-individual-life-graph-beta-prompt.md`](docs/evals/rtg-individual-life-graph-beta-prompt.md): the initial individual multi-domain life-graph beta prompt for personal and professional planning.

## Component Models

Textual SysML v2 under [`model/`](model/) is the authored black-box design for Bibliotek and
Vellis. It captures typed public actions and values, abstract owned state, action effects,
principal failures, collaborator roles, invariants, application composition, use cases, and
realizations. Human-readable pages under [`docs/model/generated/`](docs/model/generated/) are
generated projections and must not be edited as alternate specifications.

The model currently remains in shadow status: the former Markdown specifications are frozen as a
migration baseline until the remaining human model-acceptance gates pass. The pinned official Java
validator now enforces SysML syntax, linking, and semantic validation. New
contract work belongs in SysML, while known implementation disagreements are related to their
logical elements and Python realizations in
[`model/realizations/PythonImplementationDrift.sysml`](model/realizations/PythonImplementationDrift.sysml). See
[`docs/sysml-modeling.md`](docs/sysml-modeling.md) for the modeling profile and gate status.

A component model defines:

- purpose
- public values/items and provided/required actions
- abstract owned state and action read/write effects
- principal failures and no-effect guarantees
- invariants and contract-significant behavior
- verification objectives

Models use lifecycle statuses:

- `draft`: proposed boundary for discussion or early implementation
- `accepted`: human-approved and normative for implementation
- `deprecated`: valid for existing consumers, but closed to new consumers
- `retired`: historical only

Only a human owner may move a component to `accepted`, `deprecated`, or `retired`.

## Python Components

Component models are language-neutral contracts; Python is the first implementation target, not the only possible one. Other language implementations may be produced from the same model without changing its meaning.

Each component should have its own directory. By default, map component IDs to implementation directories by removing the `component.` prefix and replacing dots with path separators:

```text
component.<domain>.<name> -> components/<domain>/<name>/
```

The default shape is:

```text
components/<domain>/<name>/
  __init__.py
  protocol.py
  implementation.py
  reference.py
  tests/
    test_<domain>_<name>_contract.py
```

Use `protocol.py` for the public Python boundary, `implementation.py` for the concrete class that owns state and invariants, `reference.py` for a runnable reference composition, and `tests/` for boundary-focused verification.

## Development Setup

Vellis is consumed clone-and-run for beta testing: clone the repository and run components, apps, and tools in place. Package metadata is buildable for release validation, but no distribution is currently published.

The repo uses [`uv`](https://docs.astral.sh/uv/) for Python environment and dependency management, and [`just`](https://just.systems/) as the task runner. Python 3.14 is required, but `uv` provisions it automatically — no manual Python install needed.

Install the prerequisites and clone the repo:

```sh
# macOS
brew install uv just

# or without Homebrew
curl -LsSf https://astral.sh/uv/install.sh | sh
# just install options: https://just.systems/man/en/packages.html

git clone https://github.com/volantlabs/vellis.git
cd vellis
```

Set up the local development environment:

```sh
just setup
```

Run checks:

```sh
just check
```

Useful recipes:

- `just setup`: create or update the uv-managed `.venv`
- `just test`: run tests when tests exist
- `just lint`: run Ruff checks
- `just typecheck`: run BasedPyright checks
- `just format`: format Python code with Ruff
- `just build`: build source and wheel distributions for release validation
- `just model-setup`: fetch and verify the official Java validator, formal libraries, and Java runtime
- `just model-check`: run formal SysML validation plus architecture, realization, and generated-file checks
- `just model-check-formal`: run the pinned official SysML validator directly
- `just model-render`: regenerate model views and the static application manifest
- `just model-package`: build independently packageable shadow KPAR candidates
- `just model-handoff TARGET=<stable-id>`: inspect a model slice for an implementation handoff
- `just skills-check`: validate repo-local skill metadata
- `just skills-sync`: expose source-of-truth repo skills in Claude Code's project-skill layout
- `just rtg`: launch the RTG Knowledge Graph app with default local `.data/` storage
- `just rtg-mcp-info`: print default stdio MCP client config, prompt paths, and first-call smoke check
- `just rtg-mcp`: launch the default RTG Knowledge Graph stdio MCP server
- `just rtg-mcp-http-info`: print localhost HTTP MCP URL config for another local agent
- `just rtg-mcp-http`: launch the unauthenticated localhost HTTP MCP server
- `just rtg-eval-info`: print beta eval MCP metadata with `/tmp/vellis-beta-001` storage
- `just run-rtg-knowledge-graph`: launch the RTG Knowledge Graph app
- `just run-rtg-knowledge-graph-mcp`: launch the RTG Knowledge Graph MCP server
- `just run-rtg-knowledge-graph-mcp-info`: print RTG MCP dry-run metadata and client config
- `vellis-rtg-knowledge-graph`: installed console script for the RTG Knowledge Graph app
- `just check`: run lint, type checking, skill validation, model checks, and tests

Launch the first application with the default local `.data/` storage:

```sh
just rtg
```

When the project is installed in the uv environment, the same app is available as:

```sh
uv run vellis-rtg-knowledge-graph --json
```

Print copy-pastable MCP client metadata for the default local app:

```sh
just rtg-mcp-info
```

The metadata includes `mcp.launch_mode`, `mcp.client_config`, `mcp.transports`, prompt availability, and a
first-call smoke check. In a repository checkout, `mcp.launch_mode` is
`repository_checkout` and the generated config uses `uv --directory <repo-root>` with absolute
paths. After configuring an MCP client from `mcp.client_config`, the agent's first call should
be `rtg_validate_graph` with `{}`; a fresh app should return `ok: true` and an accepted empty
graph. The next call should be `rtg_get_system_state` with `{}`.

For modular same-machine use, run the localhost HTTP server:

```sh
just rtg-mcp-http /tmp/vellis-beta-001 127.0.0.1 8765 /mcp
```

The URL client config is in `mcp.transports.localhost_http.client_config`; the endpoint is
`http://127.0.0.1:8765/mcp`.

For a beta eval with an explicit fresh storage root:

```sh
just rtg-eval-info /tmp/vellis-beta-001
```

Run ad hoc Python commands through `uv run`:

```sh
uv run python --version
```

## Repository Guidance

Agent and contributor operating rules live in [`AGENTS.md`](AGENTS.md). In short:

- preserve component boundaries
- update specs when public behavior changes
- prefer focused, reusable components over one-off application code
- use `uv` and `just` for Python work
- verify changes at the component boundary

Repo-local agent skills live in [`.agents/skills/`](.agents/skills/). This is the source of truth for Vellis skills, including the RTG MCP usage skill. Claude Code project-skill exposure lives under [`.claude/skills/`](.claude/skills/) as symlinks back to `.agents/skills`; run `just skills-sync` to recreate those links and `just skills-check` to validate them.

## Community And Release

- License: [`Apache-2.0`](LICENSE)
- Contributing guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security reporting: [`SECURITY.md`](SECURITY.md)
- Code of conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

## Status

This repository is beta-stage. The SysML component-model system, Python project infrastructure, initial component implementations, and local RTG Knowledge Graph eval path are in place.
