# AGENTS.md

## Repository Purpose

Vellis is a library of reusable software components and tooling for AI-native software construction.

The repository should evolve in this order:

1. Build a coherent component library.
2. Add reference applications that demonstrate how components compose into software solutions.
3. Add tooling and SDK surfaces for building software from component specs.
4. Add runtime support, including distributed-runtime patterns, when the component contracts justify it.

Prefer reusable, self-contained behavior over one-off application code. Treat applications, SDKs, runtimes, and generated systems as consumers of the component library, not as reasons to weaken component boundaries.

Use text-based component specs as the bootstrap design system. They should be practical for humans and agents now while preserving the option to migrate durable structure into a knowledge graph, SysML, or another model later. Do not optimize current specs for a future ontology at the expense of clarity today.

## Startup Checks

When starting work, run:

- `pwd`
- `git status --short --branch`
- `git worktree list` when available

If this directory is not a git repository, say so and continue only for tasks that are safe without repository history. Do not assume branch or worktree state exists.

## Component-First Workflow

Use `.agents/skills/component-authoring/SKILL.md` when designing, creating, reviewing, revising, extracting, splitting, merging, or validating component specs.

Component specs live under:

```text
docs/components/
```

Use stable component IDs:

```text
component.<domain>.<name>
```

Component specs are human-owned black-box contracts. They define purpose, responsibilities, non-responsibilities, provided contracts, required contracts, owned state, invariants, verification, and agent change rules.

Do not treat component specs as implementation plans. Do not document private helper structure unless it affects public contracts, state ownership, dependencies, invariants, verification, or externally observable behavior.

Do not let a possible storage, database, transport, or persistence representation dictate a component's conceptual model or in-memory public contract. If a component could be stored in several forms, such as relational tables, documents, events, object storage, or a labeled property graph, specify the representation the component itself owns and expose only relationships that need identity, metadata, lifecycle, or independent behavior. Distinguish canonical owned state from derived indexes, caches, and projections.

For composed systems, it is valid to define a controller component that owns cross-component invariants, operation sequencing, and whole-system actions such as snapshot/restore while lower-level components own only their local record state and invariants. Keep transport adapters such as MCP, REST, CLI, and SDK outside the controller unless transport behavior is explicitly part of that component's public contract.

When a component contains several validation or policy tracks, keep the public contract whole only while one report/API is useful to consumers. Isolate tracks by source of truth, dependencies, options, and report sections so any track can later become a separate component without moving owned state or changing system behavior.

Prefer the simplest contract that serves current implementation and validation needs. Do not add alternate representations, optional abstraction layers, lifecycle states, or extension seams only because they might be useful later. Introduce them when a real consumer, invariant, or verification need makes the added surface earn its cost.

## Design Values

Favor modular, reusable, narrowly scoped components whose boundaries revolve around invariant ownership.

Good designs in this repository should be:

- Modular: responsibilities are separated when they have different owners, invariants, dependencies, or reasons to change.
- Reusable: component behavior is self-contained and useful outside a single reference app, transport, runtime, storage, or implementation-language choice.
- Narrow: each component owns a coherent responsibility and explicitly refuses adjacent behavior.
- Invariant-centered: the component that owns state or sequencing also owns the invariants that keep that state or operation valid.
- Low-coupling: components consume public contracts and avoid reaching into private internals or unrelated runtime frameworks.
- Simple and elegant: public contracts have one clear representation per operation and avoid speculative extension seams.
- Verifiable: behavior can be proven with black-box tests, contract tests, side-effect checks, and dependency checks at the component boundary.

These qualities matter because they make systems easier to understand, maintain, test, and extend. When a design choice weakens one of them, record the reason in the relevant component spec or ask for human judgment before encoding it.

## Component Status

Use these lifecycle statuses:

- `draft`: proposed boundary; useful for discussion or early implementation.
- `accepted`: human-approved boundary; normative for implementation.
- `deprecated`: still valid for existing consumers, but should not gain new consumers.
- `retired`: historical only; no active implementation should depend on it.

Only a human owner may mark a component spec `accepted`, `deprecated`, or `retired`. If ownership is unclear, keep the spec in `draft` and record the question under `Open questions`.

Accepted specs are normative over implementation convenience. If code and an accepted spec conflict, report the mismatch before changing contracts, dependencies, owned state, invariants, lifecycle status, or verification requirements.

Before a human owner marks a spec `accepted`, verify that:

- Public contracts are concrete enough for an independent implementation.
- Required and forbidden dependencies are explicit.
- Owned state and non-responsibilities are clear.
- Invariants are externally meaningful and testable.
- Verification requirements are specific enough to prove boundary behavior.
- Open questions do not leave current public behavior ambiguous.

## Agent Implementation Rules

When implementing from a component spec:

- Stay inside the component's allowed code roots unless the user explicitly approves a broader change.
- Preserve provided contracts, required contracts, owned state, invariants, and non-responsibilities.
- Add or update verification that proves behavior at the component boundary.
- Prefer black-box tests, contract tests, dependency checks, side-effect checks, and reference app tests over private helper tests alone.
- Report verification evidence in the final response.

Agents may refactor private internals inside the component boundary when public behavior and invariants are preserved.

Agents may not change accepted public contracts, add cross-component dependencies, move owned state, weaken invariants, or change runtime/deployment assumptions without explicit human approval.

## Python Component Implementation

Use `.agents/skills/python-component-implementation/SKILL.md` when implementing, reviewing, or revising Python component code from a component spec.

Python component implementations should live in one directory per component. By default, map component IDs to implementation directories by removing the `component.` prefix and replacing dots with path separators:

```text
component.<domain>.<name> -> components/<domain>/<name>/
```

The component spec's `code.roots` value is authoritative. If it differs from the mechanical mapping, treat that as intentional only when a human has approved it.

Each Python component directory should contain:

- `protocol.py`: public Python protocols, dataclasses, errors, and type aliases that define the component boundary.
- `implementation.py` or implementation modules: concrete component class implementation that owns the component's state and enforces its invariants.
- `reference.py`: a runnable reference composition that can execute on its own, using in-memory dependencies by default when the component's public contract allows that. If the component's owned state is explicitly filesystem-backed or otherwise durable, the reference may use temporary local state to preserve the contract.
- `tests/`: component boundary tests, including contract tests against the protocol and implementation-level evidence for invariants.

Prefer Python classes for component implementations. The class boundary should encapsulate the component's owned state, invariant enforcement, and public operations. Do not spread component-owned state or invariant logic across unrelated modules or reference applications.

Keep the protocol explicit and consumer-facing. Tests and reference applications should depend on the protocol shape, not on private helpers.

## Python Environment And Tasks

Use `uv` for Python environment and dependency management. The repository pins its Python version in `.python-version` and expects `uv sync --dev` to create and update the local `.venv` directory.

Use `just` as the task runner for common workflows. Prefer adding or updating `justfile` recipes over introducing ad hoc shell instructions in documentation.

Default recipes:

- `just setup`: install or update the uv-managed development environment.
- `just test`: run component and repository tests when tests exist.
- `just lint`: run Ruff checks.
- `just typecheck`: run BasedPyright checks.
- `just format`: format Python code with Ruff.
- `just skills-check`: validate repo-local skill metadata.
- `just skills-sync`: expose `.agents/skills` source-of-truth skills in Claude Code's `.claude/skills` project-skill layout.
- `just check`: run lint, type checking, skill validation, and tests.

Run Python commands through `uv run` unless there is a specific reason to use another interpreter.

## Runtime Neutrality

Component specs should define behavior and contracts before wiring choices.

Do not assume a component is in-process, dependency-injected, message-driven, distributed, packaged as a service, or backed by a specific broker such as RabbitMQ unless that is part of the public contract.

Runtime topology, transport, queueing, delivery, retry, ordering, idempotency, and consistency details belong in a spec only when they are externally meaningful to consumers.

## Language Neutrality

Component specs are language-neutral contracts. They define behavior, contracts, owned state, invariants, and verification independent of any implementation language. Python is the current first implementation target, not the definition of a component; the same spec should be implementable in another language without changing its meaning.

Keep provided and required contracts, type and error names, and verification expressed as externally observable behavior rather than language constructs, test frameworks, or tool commands. Language- and tool-specific detail — `pytest` invocations, dataclass or protocol mechanics, package layout, build commands — belongs to the implementation layer (`.agents/skills/python-component-implementation/SKILL.md` and the code), not the spec.

The durable contract a component offers is ownership of its invariants and state behind a well-defined, neutral interface. That ownership, not any wiring or language choice, is what lets components be reused and recomposed across in-process, dependency-injected, and distributed topologies and across languages.

## Reference Applications

Reference applications should demonstrate component composition. They should not become the source of truth for component behavior.

When a reference app reveals a missing or unclear component contract, update the component spec or record an open question before encoding the behavior only in the app.

Reference apps may contain glue code, adapters, and examples, but reusable behavior should move toward components.

Reference apps should expose a small composition root where component implementations are wired to app configuration. Keep configuration parsing, dependency wiring, runner behavior, and launch entry points separate enough that future components can be added without changing component internals. When a high-level controller or facade component exists for an app, the reference app should wire that component instead of owning its domain rules directly.

## Agent Skills

Repo-local agent skills live in `.agents/skills/`. Treat that directory as the source of truth for skill content.

Claude Code project-skill exposure lives in `.claude/skills/` as relative symlinks back to `.agents/skills/`. Run `just skills-sync` after adding, removing, or renaming a repo-local skill, and keep `just skills-check` passing so the Claude exposure stays aligned.

Use `.agents/skills/rtg-knowledge-graph-mcp/SKILL.md` when operating or evaluating the RTG Knowledge Graph MCP server through tools such as `rtg_validate_graph`, `rtg_apply_live_graph_changes`, `rtg_stage_knowledge_changes`, `rtg_apply_migration_cutover`, `rtg_execute_query`, snapshots, restore, or ledger replay.

## Future Repo Areas

This repo may later include folder-level guidance for areas such as:

- `docs/components/` for component specs
- `components/` or `src/` for reusable component implementations
- `apps/` for reference applications
- `sdk/` for component authoring and composition APIs
- `runtime/` for local and distributed runtime support
- `tools/` for validation, generation, and spec-to-artifact workflows

Add nested `AGENTS.md` or `AGENTS.override.md` files when a folder develops specialized rules. Keep the root file focused on repository-wide norms.

## Documentation Sync

Use `.agents/skills/documentation-sync/SKILL.md` when changes may require README, AGENTS, component specs, skills, or tooling docs to stay aligned.

When code changes affect a component's public behavior, dependencies, owned state, invariants, verification, lifecycle status, or runtime assumptions, update the related component spec in the same change.

If a code change exposes spec drift but the correct design is unclear, do not silently rewrite the spec. Record the mismatch and ask for human judgment.

## Decision Documentation

Do not create ADRs by default.

Prefer these locations for design information:

- Component-local design belongs in the component spec.
- Repo-wide operating rules belong in `AGENTS.md` or a nested `AGENTS.md`.
- Unresolved design issues belong in `Open questions` near the affected component.
- Temporary exploration belongs in the conversation or task-local notes, not durable repo docs.

Create a separate decision note only when a durable cross-component or repo-wide commitment cannot be captured cleanly in a component spec or `AGENTS.md`. Keep decision notes short, current-rule oriented, and easy to retire.

Decision notes must include:

- the current rule or constraint agents should follow
- the scope affected
- the condition that should trigger review or retirement

Do not create long historical narratives, rejected-option catalogs, or decision logs that are not needed for current engineering behavior.

## General Engineering Rules

Prefer small, focused changes that preserve component boundaries.

Use existing local conventions once they exist. Avoid introducing broad frameworks, shared abstractions, or runtime infrastructure for a single component or reference app.

Before finishing implementation work, run the narrowest relevant checks available. If no checks exist yet, say that clearly and identify what verification is missing.
