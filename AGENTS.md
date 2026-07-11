# AGENTS.md

## Repository Purpose

Vellis is a library of reusable software components and tooling for AI-native software construction.

The repository should evolve in this order:

1. Build a coherent component library.
2. Add reference applications that demonstrate how components compose into software solutions.
3. Add tooling and SDK surfaces for building software from component models.
4. Add runtime support, including distributed-runtime patterns, when the component contracts justify it.

Prefer reusable, self-contained behavior over one-off application code. Treat applications, SDKs, runtimes, and generated systems as consumers of the component library, not as reasons to weaken component boundaries.

Use textual SysML v2 under `model/` as the authored source for new component and application design. The pinned official Java validator is mandatory through `just model-check`; repository regex/profile checks are not formal language validation. Validate Foundation, Bibliotek, and Vellis from independently packaged KPAR contents, and keep the official parser-backed inventory and structured conformance objectives current through `just model-render`. The model is still marked `shadow` while the human-acceptance gates in `model/migration/cutover-status.json` remain open; the old Markdown specs under `docs/migration/component-spec-baseline/` are frozen migration evidence, not the place to author new contracts. Generated explanatory pages live under `docs/reference/`, while generated machine projections live under `generated/model/`. Do not claim final normative cutover or remove the frozen baseline before those gates pass.

Keep three separately packageable model layers: the software-component modeling foundation,
Bibliotek reusable components, and the Vellis application. In SysML terms, the foundation and
Bibliotek are reusable `library package` products; Vellis is an application `package`; KPARs are
their distribution artifacts rather than their semantic namespaces. Bibliotek may import the
foundation and Vellis may import Bibliotek; Bibliotek must never import Vellis. Preserve the logical
contracts independently of the current dependency-injected Python realization and any future
message runtime.

`model/bibliotek/Bibliotek.sysml` is Bibliotek's supported umbrella package. It publicly imports the
component packages and deliberately shared Bibliotek value packages that constitute the library
API. Keep each component in its own library package. A public type stays with the component that
owns its meaning and invariants; place it in `model/bibliotek/shared-values/` only when several
components share exactly the same semantics and no component is the natural owner. Do not place
Vellis façade values, MCP metadata, Python realization types, or speculative runtime concepts in
Bibliotek shared values.

The modeling foundation is reusable process vocabulary, not Bibliotek domain vocabulary. Keep only
minimal lifecycle, typed state-access, realization, evidence, and other generic governance conventions there. Bibliotek-wide
software/domain semantics belong in Bibliotek. Vellis-specific composition, use cases, façade
contracts, transport mappings, and response policy belong in Vellis packages.

Prefer native SysML semantics over duplicate annotations. A `perform action` is already a provided
operation. An invocation-scoped collaborator is a typed action input. A collaborator retained by a
component occurrence is a multiplicited `ref part` role; the application may bind that role to the
actual part usage because both denote the same occurrence. Never bind action usages to mean one
action calls another. Model calls as nested actions performed by provider roles, with bindings or
flows for contract-significant values. Use ordinary, `derived`, and `ref` features to distinguish owned, derived, and
independently existing state. Keep implementation bindings on concrete realization elements, not
reusable logical component definitions. Use exhibited states only for actual activated/event-driven
state behavior, and use typed ports/interfaces only when a connected interaction and its transfers
are being modeled.

Use native short names for stable qualified model identities, not as implicit serialization maps.
Use the logical literal name for a public encoding or define an explicit realization codec. Define a
calculation only when it has an evaluable result and a constraint only when it is a complete
predicate. Put every normative obligation inside a requirement `require constraint`; top-level
documentation is explanatory. Assert satisfiers separately and verify requirements only in cases
with compatible subjects. Do not create hollow calculations, constraints, states, ports, or
interfaces to hold prose. Use view definitions for reusable projections and viewpoints only for
explicit stakeholder concerns; generated Markdown is a projection.

A future message runtime should be modeled as separately packageable Bibliotek runtime contracts
only after delivery, addressing, routing, correlation, ordering, retry, and idempotency semantics
are intentionally designed for reuse. Vellis may then add a message-runtime realization that maps
the same logical component capabilities to ports, messages, and flows. Do not rewrite today's
component actions or collaborator roles merely because their realization changes from direct
calls to messaging.

## Startup Checks

When starting work, run:

- `pwd`
- `git status --short --branch`
- `git worktree list` when available

If this directory is not a git repository, say so and continue only for tasks that are safe without repository history. Do not assume branch or worktree state exists.

## Model-First Component Workflow

Use `.agents/skills/component-authoring/SKILL.md` when designing, creating, reviewing, revising,
extracting, splitting, merging, or validating components. Author the component contract in
`model/bibliotek/components/` and application composition in `model/vellis/`; run
`just model-render` for human-readable projections. Do not hand-edit generated pages.

During migration, a semantic mismatch with the frozen Markdown baseline or current implementation
is a review finding, not permission to rewrite an accepted boundary. Surface genuine implementation
disagreement for human review before changing accepted contracts, state ownership, dependencies,
invariants, lifecycle status, or public behavior; after a decision, align the model, realization,
and conformance evidence together.

Before deleting the frozen baseline, disposition its durable content rather than relying only on
surface-name parity: contractual facts belong in SysML; useful rationale, operations, evolution
notes, and unresolved questions belong in clearly non-normative documentation; superseded prose
must be traceable to the current model decision; and implementation-time contract discoveries must
be modeled deliberately or remain an explicit unresolved engineering decision outside the accepted
contract.

Use stable component IDs:

```text
component.<domain>.<name>
```

Component models are human-owned black-box contracts. They define purpose, public values/items,
performed actions, action-scoped inputs, retained collaborator roles, abstract owned state,
action effects, principal failures, invariants,
required constraints, asserted satisfiers, and subject-compatible verification objectives. Stop at the level needed for composition, substitution, design-level
reasoning, and black-box verification.

The model is the living engineering definition, not a summary of the Python implementation. Judge
Python, Rust, or any other realization by conformance at the modeled boundary rather than internal
similarity. Apply the same rule recursively: Bibliotek component realizations conform to component
contracts; Vellis roles conform to Bibliotek; the composed Vellis application conforms to its own
façade, use-case, behavior, and invariant contracts. Model implementation algorithms, deployments,
or hardware only when they become intentional engineering subjects or affect an observable
contract.

When migrating an accepted contract into SysML, preservation is a gate before simplification. Keep
exact public field names, types, multiplicities, defaults, construction actions, concrete failure
families, state categories, ordering promises, and observable effects unless a human explicitly
approves a contract change. Do not interpret “right-sized” as permission to collapse typed values
into generic JSON, merge distinct failures, omit derived state, or replace exact behavior with a
broader summary that admits incompatible implementations.

Before treating a component model as source-of-truth ready, verify that its generated page is at
least as useful as the accepted predecessor for implementing, composing, and black-box testing the
component. A checker that finds a similarly named action is not sufficient; signature, defaults,
results, failures, state access, dependencies, invariants, and verification closure must agree.

Do not treat component models as executable implementation plans. Do not model private helpers,
AST/call graphs, implementation branches, algorithms, storage layouts, Python exception
inheritance, or equivalent internal structures unless they affect observable contract behavior.

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

These qualities matter because they make systems easier to understand, maintain, test, and extend. When a design choice weakens one of them, record the reason near the relevant model element or ask for human judgment before encoding it.

## Component Status

Use these lifecycle statuses:

- `draft`: proposed boundary; useful for discussion or early implementation.
- `accepted`: human-approved boundary; normative for implementation.
- `deprecated`: still valid for existing consumers, but should not gain new consumers.
- `retired`: historical only; no active implementation should depend on it.

Only a human owner may mark a component model `accepted`, `deprecated`, or `retired`. If ownership is unclear, keep it in `draft` and record the question in model documentation or a nearby non-normative note.

Accepted models are normative over implementation convenience after cutover. During shadow mode,
preserve accepted boundaries and record disagreements explicitly before changing contracts,
dependencies, owned state, invariants, lifecycle status, or verification requirements.

Before a human owner marks a spec `accepted`, verify that:

- Public contracts are concrete enough for an independent implementation.
- Required and forbidden dependencies are explicit.
- Owned state and non-responsibilities are clear.
- Invariants are externally meaningful and testable.
- Verification requirements are specific enough to prove boundary behavior.
- Open questions do not leave current public behavior ambiguous.

During the current shadow migration, the same checklist applies before approving model cutover,
and every accepted predecessor obligation must either be represented, explicitly excluded as
non-normative, or approved as a contract change.

## Agent Implementation Rules

When implementing from a component model:

- Stay inside the component's allowed code roots unless the user explicitly approves a broader change.
- Preserve provided contracts, required contracts, owned state, invariants, and non-responsibilities.
- Add or update verification that proves behavior at the component boundary.
- Prefer black-box tests, contract tests, dependency checks, side-effect checks, and reference app tests over private helper tests alone.
- Report verification evidence in the final response.

Agents may refactor private internals inside the component boundary when public behavior and invariants are preserved.

Agents may not change accepted public contracts, add cross-component dependencies, move owned state, weaken invariants, or change runtime/deployment assumptions without explicit human approval.

## Python Component Implementation

Use `.agents/skills/python-component-implementation/SKILL.md` when implementing, reviewing, or revising Python component code from accepted SysML/KPAR, generated views, and verification objectives.

Python component implementations should live in one directory per component. By default, map component IDs to implementation directories by removing the `component.` prefix and replacing dots with path separators:

```text
component.<domain>.<name> -> components/<domain>/<name>/
```

The concrete realization's `ImplementationBinding.codeRoot` is authoritative. Logical Bibliotek
component definitions remain language- and runtime-neutral. If a realization binding differs from
the mechanical mapping, treat that as intentional only when a human has approved it.

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
- `just model-setup`: fetch and checksum-verify the pinned official validator, formal libraries, and Java runtime.
- `just model-check`: run official SysML validation plus profile, architecture, implementation-binding, and generated-artifact checks.
- `just model-check-formal`: run the pinned official SysML validator directly.
- `just model-render`: regenerate model-derived documentation views and the static Vellis application manifest.
- `just model-package`: build independently packageable shadow KPAR candidates.
- `just model-handoff TARGET=<stable-id>`: inspect the model slice and verification objectives for an implementation handoff.
- `just check`: run lint, type checking, skill validation, model checks, and tests.

Run Python commands through `uv run` unless there is a specific reason to use another interpreter.

## Runtime Neutrality

Component models should define behavior and contracts before wiring choices.

Do not assume a component is in-process, dependency-injected, message-driven, distributed, packaged as a service, or backed by a specific broker such as RabbitMQ unless that is part of the public contract.

Runtime topology, transport, queueing, delivery, retry, ordering, idempotency, and consistency details belong in a spec only when they are externally meaningful to consumers.

## Language Neutrality

Component models are language-neutral contracts. They define behavior, contracts, owned state, invariants, and verification independent of any implementation language. Python is the current first implementation target, not the definition of a component; the same model should be implementable in another language without changing its meaning.

Keep provided and required contracts, type and error names, and verification expressed as externally observable behavior rather than language constructs, test frameworks, or tool commands. Language- and tool-specific detail — `pytest` invocations, dataclass or protocol mechanics, package layout, build commands — belongs to the implementation layer (`.agents/skills/python-component-implementation/SKILL.md` and the code), not the spec.

The durable contract a component offers is ownership of its invariants and state behind a well-defined, neutral interface. That ownership, not any wiring or language choice, is what lets components be reused and recomposed across in-process, dependency-injected, and distributed topologies and across languages.

## Reference Applications

Reference applications should demonstrate component composition. They should not become the source of truth for component behavior.

When a reference app reveals a missing or unclear component contract, update the component model or record an open question before encoding the behavior only in the app.

Reference apps may contain glue code, adapters, and examples, but reusable behavior should move toward components.

Reference apps should expose a small composition root where component implementations are wired to app configuration. Keep configuration parsing, dependency wiring, runner behavior, and launch entry points separate enough that future components can be added without changing component internals. When a high-level controller or facade component exists for an app, the reference app should wire that component instead of owning its domain rules directly.

## Agent Skills

Repo-local agent skills live in `.agents/skills/`. Treat that directory as the source of truth for skill content.

Claude Code project-skill exposure lives in `.claude/skills/` as relative symlinks back to `.agents/skills/`. Run `just skills-sync` after adding, removing, or renaming a repo-local skill, and keep `just skills-check` passing so the Claude exposure stays aligned.

Use `.agents/skills/rtg-knowledge-graph-mcp/SKILL.md` when operating or evaluating the RTG Knowledge Graph MCP server through tools such as `rtg_validate_graph`, `rtg_apply_live_graph_changes`, `rtg_stage_knowledge_changes`, `rtg_apply_migration_cutover`, `rtg_execute_query`, snapshots, restore, or ledger replay.

## Future Repo Areas

This repo may later include folder-level guidance for areas such as:

- `model/bibliotek/` for reusable component models
- `model/vellis/` for application composition and realizations
- `docs/reference/` for generated human views
- `generated/model/` for generated parser, conformance, and evidence data
- `components/` or `src/` for reusable component implementations
- `apps/` for reference applications
- `sdk/` for component authoring and composition APIs
- `runtime/` for local and distributed runtime support
- `tools/` for validation, generation, and spec-to-artifact workflows

Add nested `AGENTS.md` or `AGENTS.override.md` files when a folder develops specialized rules. Keep the root file focused on repository-wide norms.

## Documentation Sync

Use `.agents/skills/documentation-sync/SKILL.md` when changes may require README, AGENTS, component models, generated views, skills, or tooling docs to stay aligned.

When code changes affect a component's public behavior, dependencies, owned state, invariants, verification, lifecycle status, or runtime assumptions, update the related SysML model in the same change and regenerate its views.

If a code change exposes spec drift but the correct design is unclear, do not silently rewrite the spec. Record the mismatch and ask for human judgment.

## Decision Documentation

Do not create ADRs by default.

Prefer these locations for design information:

- Component-local design belongs in the component model.
- Repo-wide operating rules belong in `AGENTS.md` or a nested `AGENTS.md`.
- Unresolved design issues belong near the affected model element in concise non-normative documentation.
- Temporary exploration belongs in the conversation or task-local notes, not durable repo docs.

Create a separate decision note only when a durable cross-component or repo-wide commitment cannot be captured cleanly in the model or `AGENTS.md`. Keep decision notes short, current-rule oriented, and easy to retire.

Decision notes must include:

- the current rule or constraint agents should follow
- the scope affected
- the condition that should trigger review or retirement

Do not create long historical narratives, rejected-option catalogs, or decision logs that are not needed for current engineering behavior.

## General Engineering Rules

Prefer small, focused changes that preserve component boundaries.

Use existing local conventions once they exist. Avoid introducing broad frameworks, shared abstractions, or runtime infrastructure for a single component or reference app.

Before finishing implementation work, run the narrowest relevant checks available. If no checks exist yet, say that clearly and identify what verification is missing.
