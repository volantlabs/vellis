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

Install Git and `uv`, clone the repo, and enter the checkout. You do not need to install Python or
`just`: `uv` provisions the required Python and locked runtime dependencies automatically.

```sh
# macOS (Homebrew)
brew install git uv

# macOS/Linux (standalone uv installer)
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/volantlabs/vellis.git
cd vellis
```

On native Windows, use PowerShell:

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
# Open a new PowerShell window after installation.
git clone https://github.com/volantlabs/vellis.git
cd vellis
```

Run setup. The first `uv run` may download Python and dependencies; later runs reuse them.

```sh
uv run vellis setup
```

Setup detects Codex, Claude Code, or Claude Desktop, shows its intended user-wide MCP change, asks
once, recovers any existing durable graph, and installs the modeled Everyday Life schema only when
the graph is genuinely empty. It never invents people, tasks, or other facts. Restart or reload the
selected client, then say:

> Help me start using Vellis to remember and organize things across my personal life, household or
> family responsibilities, and work. Use the schema already installed. Ask before assuming missing
> details and show me what you propose before making a large initial write.

That is the complete ordinary setup path—no MCP JSON editing, raw tool calls, schema construction,
or snapshots are required. State is stored unencrypted under `.data/rtg_knowledge_graph/`, ignored
by Git, and recovered automatically across MCP process restarts. See the
[plain-language getting-started guide](docs/guides/vellis/getting-started.md) for backups, reset,
troubleshooting with `uv run vellis doctor`, shared-family use, and advanced local HTTP mode.

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

The [model-based engineering vision](docs/vision/agentic-mbse-engineering-system.md) explains how
humans can focus on intent and architectural judgment while agents help maintain the model,
realizations, projections, and verification evidence.

## Current Focus

Vellis evolves in this order:

1. Build a coherent component library.
2. Ship Vellis as the first turnkey application assembled from those components.
3. Add tooling and SDK surfaces for building software from component models.
4. Add runtime support, including distributed-runtime patterns, when component contracts justify it.

Current generated component views include:

- [Bibliotek model reference](generated/reference/bibliotek/index.md): library packages, components,
  shared values, and retained dependency topology.

- [`component.storage.json_file`](generated/reference/bibliotek/components/component.storage.json_file.md): local filesystem-backed JSON document storage.
- [`component.storage.sql`](generated/reference/bibliotek/components/component.storage.sql.md): SQLite-backed generic SQL execution surface for durable relational storage consumers.
- [`component.rtg.graph`](generated/reference/bibliotek/components/component.rtg.graph.md): schema-neutral in-memory reified type graph for anchors, data objects, links, and direct UUID indexes.
- [`component.rtg.schema`](generated/reference/bibliotek/components/component.rtg.schema.md): RTG-native schema-definition store for live and non-live anchor, data object, and link definitions.
- [`component.rtg.constraints`](generated/reference/bibliotek/components/component.rtg.constraints.md): constraint-definition store for RTG graph-pattern and lifecycle rules.
- [`component.rtg.migration`](generated/reference/bibliotek/components/component.rtg.migration.md): migration records that track schema, constraint, and graph lifecycle cutover sets.
- [`component.rtg.change_validation`](generated/reference/bibliotek/components/component.rtg.change_validation.md): batch validator with isolated validation tracks.
- [`component.rtg.query`](generated/reference/bibliotek/components/component.rtg.query.md): declarative graph query evaluator.
- [`component.rtg.discovery`](generated/reference/bibliotek/components/component.rtg.discovery.md): draft curated discovery-view component.
- [`component.rtg.controller`](generated/reference/bibliotek/components/component.rtg.controller.md): cross-component orchestration and invariant owner.

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
  wires JSON File Storage, SQL Storage, and the in-process RTG controller, then exposes the modeled
  Vellis façade through local MCP transports for human/agent knowledge-system workflows.
- [Vellis application model reference](generated/reference/vellis/index.md): composition, actor-visible
  use cases, façade requirements, verification, and MCP realization mappings.

The RTG Knowledge Graph MCP server uses standalone FastMCP v3 from the `fastmcp` package.

Manual evaluation prompts include:

- [`docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md`](docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md): a compact known-good walkthrough for the default life-graph beta path.
- [`docs/guides/vellis/evals/rtg-broad-beta-gates.md`](docs/guides/vellis/evals/rtg-broad-beta-gates.md): the separate repo-blind, ordinary-onboarding, and existing-beta upgrade gates for broad beta.
- [`docs/guides/vellis/evals/rtg-agent-affordance-eval-prompt.md`](docs/guides/vellis/evals/rtg-agent-affordance-eval-prompt.md): a copy-pastable agent eval for using RTG as an evolving memory, knowledge graph, and database.
- [`docs/guides/vellis/evals/rtg-agent-affordance-eval-runbook.md`](docs/guides/vellis/evals/rtg-agent-affordance-eval-runbook.md): launch and prompt-sequencing guidance for running the RTG MCP eval.
- [`docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md`](docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md): the initial individual multi-domain life-graph beta prompt for personal and professional planning.

## Component Models

Textual SysML v2 under [`model/`](model/) is the normative black-box design for Bibliotek and
Vellis. It captures typed public actions and values, abstract owned state, action effects,
principal failures, collaborator roles, invariants, application composition, use cases, and
realizations. Human-readable pages under [`generated/reference/`](generated/reference/) are
generated projections and must not be edited as alternate specifications.

Textual SysML is the normative design authority. The pinned official Java validator enforces SysML
syntax, linking, and semantic validation. Reviewed implementation disagreements have been resolved
in the model and Python realization; future disagreements must return through model review instead
of silently changing either side. See the non-normative
[open model-design questions](docs/design/open-design-questions.md) for possible future evolution and
[`docs/engineering/sysml-modeling.md`](docs/engineering/sysml-modeling.md) for the modeling profile.

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
just model-setup
```

`just model-setup` downloads and checksum-verifies the pinned model references and validator assets
required by the model checks. Run it once after cloning and again when the model lock files change.

Then run checks:

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
- `just model-reference-render`: regenerate searchable SysML/KerML pages from pinned official PDFs
- `just model-reference-check`: verify the committed specification corpus against those PDFs
- `just model-reference-find "<question>"`: find ranked SysML/KerML sections and source pages
- `just model-check`: validate packaged model products plus architecture, realization, and generated files
- `just model-check-formal`: run the pinned official SysML validator directly
- `just model-render`: regenerate the parser inventory, conformance objectives, views, and manifest
- `just model-package`: build independently packageable KPAR products
- `just model-diff`: review authored model, generated projection, and runtime-manifest changes
- `just model-handoff TARGET=<stable-id>`: inspect a model slice for an implementation handoff
- `just model-audit [stable-id]`: collect an advisory model/implementation drift evidence bundle
- `just skills-check`: validate repo-local skill metadata
- `just skills-sync`: expose source-of-truth repo skills in Claude Code's project-skill layout
- `just rtg`: launch the RTG Knowledge Graph app with default local `.data/` storage
- `uv run vellis setup`: install/recover the starter schema and configure a local MCP client
- `uv run vellis doctor`: non-destructively inspect local state and client registration
- `just rtg-mcp-config`: print only copy-pastable stdio MCP client configuration
- `just rtg-mcp-info`: print default stdio MCP client config, prompt paths, and first-call smoke check
- `just rtg-mcp`: launch the default RTG Knowledge Graph stdio MCP server
- `just rtg-mcp-http-info`: print localhost HTTP MCP URL config for another local agent
- `just rtg-mcp-http`: launch the unauthenticated localhost HTTP MCP server
- `just rtg-eval-info`: print detailed beta eval MCP metadata with `.data/vellis-beta-001` storage
- `just run-rtg-knowledge-graph`: launch the RTG Knowledge Graph app
- `just run-rtg-knowledge-graph-mcp`: launch the RTG Knowledge Graph MCP server
- `just run-rtg-knowledge-graph-mcp-info`: print RTG MCP dry-run metadata and client config
- `vellis`: short console script for setup, doctor, and the RTG Knowledge Graph app
- `vellis-rtg-knowledge-graph`: preserved compatibility console script
- `just check`: run lint, type checking, skill validation, model checks, and tests

Launch the first application with the default local `.data/` storage:

```sh
just rtg
```

When the project is installed in the uv environment, the same app is available as:

```sh
uv run vellis-rtg-knowledge-graph --json
```

For protocol debugging only, print MCP client configuration for the default local app:

```sh
just rtg-mcp-config
```

The output is the complete `mcpServers` JSON block. It uses absolute executable, repository,
storage, and SQLite paths so GUI clients do not need to inherit your shell's working directory or
`PATH`. The MCP client starts the configured stdio server; do not also run `just rtg` or
`just rtg-mcp`. An ordinary app recovers durable state and reports the installed starter schema.
Use `just rtg-mcp-info` only when you need the larger diagnostic payload containing prompt
paths, transports, tool metadata, and the smoke-check expectation.

For modular same-machine use, run the localhost HTTP server:

```sh
just rtg-mcp-http .data/vellis-beta-001 127.0.0.1 8765 /mcp
```

The URL client config is in `mcp.transports.localhost_http.client_config`; the endpoint is
`http://127.0.0.1:8765/mcp`.

For a developer beta eval with explicit blank/manual-recovery state:

```sh
just rtg-eval-info .data/vellis-beta-001
```

Run ad hoc Python commands through `uv run`:

```sh
uv run python --version
```

## Repository Guidance

Agent and contributor operating rules live in [`AGENTS.md`](AGENTS.md). In short:

- preserve component boundaries
- update the normative SysML model when public behavior changes
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
