# Vellis

Vellis is an individually owned personal AI system and an open demonstration of model-first software engineering with textual SysML v2.

The repository currently contains the Vellis system model and its development tooling, with no application implementation or generated product source yet. The model covers owner-facing behavior, Reified Type Graph (RTG) graph and query meaning, ledger-authoritative state and scalable history access, canonical equality and string-shape constraints, cold-agent current or historical definition discovery, definition governance, blank or recommended Everyday Life initialization, confirmed first-use import from a Vellis v1 JSON snapshot, snapshots and replay, proactive owner-visible analysis support, a selected ten-tool MCP contract, cohesive system responsibility, requirements, satisfiers, analysis, and verification cases.

## What is here

- [`model/`](model/): the textual SysML packages forming the current system authority.
- [`docs/vision.md`](docs/vision.md): the human/agent engineering vision.
- [`docs/modeling-method.md`](docs/modeling-method.md): the use-case-first model-as-code method.
- [`docs/implementation-method.md`](docs/implementation-method.md): the bidirectional path from
  accepted model meaning to code and conformance evidence.
- [`docs/mcp-realization.md`](docs/mcp-realization.md): non-normative guidance for a future FastMCP realization.
- [`model/config/`](model/config/): checksum pins for the specifications, model libraries, and validator. The searchable corpus is generated from them into an ignored cache, never committed.
- [`.agents/skills/`](.agents/skills/): a portable SysML v2 MBSwE core plus Vellis-specific domain
  and repository extensions.
- [`implementation-campaign.yaml`](implementation-campaign.yaml): the baseline-bound current plan
  and execution/evidence index for the future application build; it is not product authority.
- [`tools/`](tools/): the pinned validator, reference search, skill checks, and campaign validation.

`just model-setup` builds a searchable SysML v2 reference layer into an ignored cache: the pinned
specifications, the normative model libraries, and 309 validated example models, all searched
together with each result labelled by source. The `$sysml-reference` skill carries a map from
ordinary engineering intent to SysML construct names, so an agent can name what it needs before
searching.

The SysML on a branch is that branch's system definition. A pull request proposes changes to behavior, requirements, system responsibility, and verification; review and merge are the acceptance mechanism. Markdown explains the work without duplicating the model as a parallel contract.

## Agent-assisted engineering

Begin with [`AGENTS.md`](AGENTS.md), then read the [model map](model/README.md), every current `model/*.sysml` file, and the current diff. Use `$sysml-modeling` for the engineering workflow, `$sysml-reference` for language decisions, `$rtg-schema-design` for RTG domain and governance meaning, and `$documentation-sync` after model or workflow changes.

The reusable core is `$sysml-reference`, `$sysml-modeling`,
`$sysml-implementation-planning`, `$sysml-implementation`, and
`$sysml-implementation-campaign`. Together they define a domain-neutral evidence, modeling,
whole-model decomposition, bounded realization, conformance, resumable execution, and closure loop.
They deliberately do not assume Vellis, RTG, this repository's paths or commands, Git, Python, MCP,
persistence, networking, code generation, or a test framework.

`AGENTS.md`, the model map, the pinned tooling, and the `just` commands bind that portable method
to this repository. `$rtg-schema-design` adds Vellis's RTG semantics, while
`$documentation-sync` maintains this repository's public and contributor guidance. Those are
optional project and domain extensions, not dependencies of the portable core. No standalone plugin
is packaged yet; the core skills are written so they can be moved or packaged later without carrying
the Vellis binding into another project.

For a complete-system build, `$sysml-implementation-planning` reads the complete accepted model and
derives dependency-ordered, evidence-bearing semantic slices. The committed campaign record remains
awaiting human approval until that complete plan is accepted. A continuation harness may then invoke
`$sysml-implementation-campaign`, which selects one ready slice, uses `$sysml-implementation`, runs
independent review and remediation to a fixed point, checkpoints the slice with the ledger update,
and repeats through whole-system runnable closure. The complete campaign receives one human
approval; reviewed routine slice checkpoints continue autonomously unless a model, plan, baseline,
feasibility, or external-authority boundary requires renewed human direction.

For Codex, launch that approved campaign as a [long-running goal](https://learn.chatgpt.com/use-cases/follow-goals)
whose objective is campaign completion and whose stopping conditions are the campaign skill's human
authority boundaries. An equivalent continuation harness may be used elsewhere; the committed
campaign record, rather than one agent conversation, remains the resume authority.

When an accepted semantic slice is ready for code, model work emits a compact handoff of qualified
authority, in-scope obligations, authority coverage, remaining obligations, decisive examples,
conformance-evidence intent, and deliberately open realization decisions. `$sysml-implementation`
verifies or reconstructs that frame, selects the simplest evidence-backed realization, implements one
end-to-end slice, and returns conformance evidence or precisely classified feedback. The handoff is a
navigation aid, not another contract; the branch's SysML remains authoritative.

A useful handoff answers the question, states the changed or reviewed meaning, gives decisive evidence and checks, and names only the remaining decision or follow-up work. An agent unfamiliar with an RTG begins with the modeled definition summary for current or selected historical state, then inspects only the active anchor neighborhoods needed for its query or proposed change. It retrieves the sole proposed definition set separately when continuing current definition work.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/). `git` is also required, since `model-setup` fetches the pinned upstream release as a sparse checkout. Then run:

```sh
just setup
just model-setup
just check
```

Useful commands:

- `just model-check`: validate every authored SysML file with the pinned validator.
- `just model-reference-find "<question>"`: search the specifications, model libraries, and example models; every hit is labelled with its source. Supply optional filters positionally, for example `just model-reference-find "<question>" sysml-2.1 8`.
- `just model-reference-concepts`: list every SysML v2 construct name, for turning a question into a searchable term.
- `just model-probe "<snippet>"`: check one SysML snippet against the pinned parser in about six seconds.
- `just model-reference-check`: prove the generated search corpus still matches its pin.
- `just skills-check`: validate the repo-local skills and their managed project links.
- `just implementation-campaign-check`: validate the campaign schema, baseline, qualified model
  references, dependency graph, approval, evidence, and closure invariants.
- `just implementation-campaign-status`: show campaign freshness, approval, active or next slice,
  blockers, and closure status.
- `just implementation-campaign-baseline`: print the currently observed model, language, and
  validator digests without changing files.
- `just implementation-campaign-checkpoint-check`: after a checkpoint commit, prove its identifier,
  review trailers, evidence, and committed campaign state resolve together.
- `just check`: run the complete repository gate.

The model and campaign method are selected, but the application implementation remains absent,
unverified, and not runnable. The model selects a portable MCP tool contract but does not implement
an MCP server. The current implementation plan directly pins FastMCP and FastMCP Slim 4.0.0b1,
selects local STDIO, and selects a future documented Python setup path; none is installed or runnable
yet. Storage layout, deployment, and migration realization remain open. The initial contract assumes
one trusted owner-configured client; its tools do not implement per-call authorization or decide
owner approval. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow.
