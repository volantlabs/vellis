# Vellis

Vellis is an individually owned personal AI system and an open demonstration of model-first software engineering with textual SysML v2.

The repository currently contains the Vellis system model and its development tooling, with no application implementation or generated product source yet. The model covers owner-facing behavior, Reified Type Graph (RTG) graph and query meaning, cold-agent definition discovery, definition governance, snapshots and replay, a selected MCP tool contract, cohesive system responsibility, requirements, satisfiers, and verification cases.

## What is here

- [`model/`](model/): five ordered SysML packages forming the current system authority.
- [`docs/vision.md`](docs/vision.md): the human/agent engineering vision.
- [`docs/modeling-method.md`](docs/modeling-method.md): the use-case-first model-as-code method.
- [`docs/mcp-realization.md`](docs/mcp-realization.md): non-normative guidance for a future FastMCP realization.
- [`model/config/`](model/config/): checksum pins for the specifications, model libraries, and validator. The searchable corpus is generated from them into an ignored cache, never committed.
- [`.agents/skills/`](.agents/skills/): four complementary engineering-copilot skills.
- [`tools/`](tools/): the pinned validator, reference finder, and skill checks.

The SysML on a branch is that branch's system definition. A pull request proposes changes to behavior, requirements, system responsibility, and verification; review and merge are the acceptance mechanism. Markdown explains the work without duplicating the model as a parallel contract.

## Agent-assisted modeling

Begin with [`AGENTS.md`](AGENTS.md), then read the [model map](model/README.md), every current `model/*.sysml` file, and the current diff. Use `$sysml-modeling` for the engineering workflow, `$sysml-reference` for language decisions, `$rtg-schema-design` for RTG domain and governance meaning, and `$documentation-sync` after model or workflow changes.

A useful handoff answers the question, states the changed or reviewed meaning, gives decisive evidence and checks, and names only the remaining decision or follow-up work. An agent unfamiliar with an RTG begins with the modeled current definition summary, then inspects only the active anchor neighborhoods needed for its query or proposed change.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/), then run:

```sh
just setup
just model-setup
just check
```

Useful commands:

- `just model-check`: validate every authored SysML file with the pinned validator.
- `just model-reference-find "<question>"`: find relevant specification pages.
- `just model-reference-find "<question>" sysml-2.0 5`: limit a search by specification and count.
- `just model-reference-check`: prove the generated search corpus still matches its pin.
- `just skills-check`: validate the four repo-local skills and their managed project links.
- `just check`: run the complete repository gate.

The model selects ten portable MCP tool behaviors but does not implement an MCP server. Runtime,
storage, transport, deployment, and migration realization remain open. The initial contract assumes
one trusted owner-configured client; its tools do not implement per-call authorization or decide owner
approval. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow.
