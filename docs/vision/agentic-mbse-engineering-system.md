# Agentic MBSE Engineering System

## Purpose

This note captures a working thesis for an agentic engineering system built around a durable model, not around disconnected documents, tickets, plans, and implementation artifacts.

The former Markdown component specs are the frozen bootstrap representation. The selected target
is committed textual SysML v2: a native-first model that agents and humans use to design,
implement, validate, and ship Bibliotek components and Vellis applications with stronger cohesion
and traceability. During migration the model remains in shadow status until formal validation and
human acceptance; new design is authored in SysML and prose is generated from it.

## Thesis

Agents should help humans focus on the highest-ROI parts of engineering:

- creative system design
- high-level cohesion and boundary judgment
- low-level constraint and invariant capture where it matters
- product and user-experience judgment
- behavioral and visual validation of deliverables
- acceptance decisions

Agents should absorb more of the mechanical work:

- translating intent into structured model changes
- generating code from accepted patterns and model contracts
- producing tests and fixtures
- updating projections such as docs and task views
- checking consistency and change impact
- running validation loops
- gathering evidence

The slowest part of engineering has often been writing code and surrounding artifacts by hand. Much of that work is translation labor: turning intent into structure, structure into APIs, APIs into implementation, implementation into tests, and behavior into documentation. Agents can perform much of that translation when the system gives them clear intent, durable constraints, and tight validation feedback.

## Target State

The engineering system should have a canonical model that connects:

- MBSE model elements: components, contracts, interfaces, dependencies, constraints, invariants, behaviors, and requirements.
- Product artifacts: user goals, workflows, features, acceptance criteria, UX states, and visual references.
- Testing artifacts: verification cases, test suites, scenarios, fixtures, visual checks, behavioral evidence, and coverage.
- Implementation links: repositories, code roots, modules, public APIs, commits, pull requests, generated files, and ownership.
- Task stream: work items, planned changes, blockers, review status, release readiness, and cutover state.
- Evidence: test runs, screenshots, traces, validation reports, design reviews, human approvals, and release decisions.

These should not be merely prose documents with hyperlinks. They should be typed model objects with explicit relationships and constraints.

## Why A Model

A durable model changes the engineering substrate.

Without a model, agents repeatedly reconstruct intent from prose, code, git history, tickets, and local context. With a model, agents can query a persistent external working memory that contains system structure, constraints, traceability, and evidence.

The model should answer questions such as:

- Which components depend on this contract?
- What tests prove this invariant?
- Which product workflows are affected by this change?
- Which accepted model elements lack implementation evidence?
- Which tasks are blocked by unresolved design questions?
- What changed between model versions?
- What can be generated safely?
- What requires human judgment?
- What work remains before this feature or release can ship?

## Human And Agent Roles

Humans should steer the model through intent, constraints, priorities, tradeoffs, and acceptance judgment.

Examples:

- "Make this reusable."
- "Split this by invariant ownership."
- "Show the impact of changing this contract."
- "Prepare a migration for this model change."
- "Why is this invariant unproven?"
- "Validate whether this workflow satisfies the intended user experience."
- "Make the model consistent with this design decision."

Agents should operate the model:

- propose model changes
- validate proposed changes
- generate code and tests from accepted model slices
- update projections
- gather evidence
- explain impact
- surface conflicts and open questions
- maintain traceability

Humans should not need to author raw SysML, graph records, or Markdown specs by hand. Agents should manage that complexity while keeping human judgment in the loop.

## Canonical Model Scope

The first useful model should be narrower than a full systems-engineering universe. It should begin with the concepts already proven useful in the component models:

- `Component`
- `ProvidedContract`
- `RequiredContract`
- `Responsibility`
- `NonResponsibility`
- `OwnedState`
- `Invariant`
- `VerificationRequirement`
- `VerificationEvidence`
- `OpenQuestion`
- `ImplementationRoot`
- `Dependency`
- `ChangeRule`
- `ModelChange`
- `Task`
- `ReviewFinding`

Additional product and delivery concepts can be added as they become needed:

- `UserGoal`
- `Workflow`
- `Feature`
- `AcceptanceCriterion`
- `VisualReference`
- `Scenario`
- `ReleaseCandidate`
- `Blocker`

The model should stay simple. Add new concepts when they unlock validation, traceability, generation, planning, or review value.

## Relationship Examples

Useful relationships include:

- A `Component` provides a `ProvidedContract`.
- A `Component` requires a `RequiredContract`.
- A `ProvidedContract` is implemented by an `ImplementationRoot`.
- An `Invariant` constrains a `Component`, `Contract`, or `Workflow`.
- A `VerificationRequirement` verifies an `Invariant`.
- `VerificationEvidence` satisfies a `VerificationRequirement`.
- A `Feature` depends on components and workflows.
- A `Task` changes specific model elements and implementation roots.
- A `ReviewFinding` blocks acceptance of a model change.
- A `ReleaseCandidate` requires specific evidence before release.
- A `Migration` changes lifecycle state for model, graph, or implementation artifacts.

## Standards And Language Alignment

SysML v2 is the likely reference standard for the MBSE side of the model because it covers requirements, structure, behavior, analysis, and verification. KerML is useful as the conceptual foundation behind SysML v2.

The canonical form should use native SysML constructs plus ordinary typed governance metadata,
not a custom language or implicit specialization. The software-component modeling foundation adds
metadata for the repository concepts that SysML does not itself govern:

- component boundary
- invariant ownership
- non-responsibility
- allowed and forbidden dependency
- implementation root
- agent change rule
- acceptance readiness
- verification evidence
- migration and cutover state

Other standards may be useful as projections or imports:

- SHACL-style constraints for graph validation patterns.
- SACM or GSN-style assurance concepts for claims, arguments, and evidence.
- ReqIF for requirements exchange with external tools.
- ArchiMate for enterprise architecture views.
- UML, C4, or similar diagram styles for developer-facing projections.

The practical stance is:

Use textual SysML v2.0 committed to Git as the semantic source of truth after the migration gates
pass. Use RTG as a potential query, projection, or collaboration realization—not as a second
canonical representation. Keep the foundation, Bibliotek, and Vellis independently packageable.

## Artifact Policy

Every durable engineering artifact should ideally be one of:

- canonical model data
- generated projection from model data
- evidence linked to model data
- external artifact linked to model data with clear ownership

Avoid orphan artifacts:

- orphan docs
- orphan tickets
- orphan screenshots
- orphan test reports
- orphan code notes
- orphan diagrams

Disconnected artifacts should either be imported into the model, linked as evidence, or treated as temporary working notes.

## System Layers

A full implementation would likely need these layers:

1. Canonical model layer: textual SysML v2 stores typed engineering model elements in Git.
2. Language and profile layer: a pinned formal validator plus repository architecture checks
   validate language and component-model integrity.
3. Controller layer: applies validated changes, snapshots, migrations, and cutovers.
4. Projection layer: generates explanatory Markdown pages, diagrams, reports, implementation handoffs, task views, and release summaries.
5. Evidence ingestion layer: imports test runs, traces, screenshots, code analysis, commits, pull requests, and review decisions.
6. Planning/task layer: turns model deltas and unresolved requirements into work items and execution streams.
7. Human interface layer: conversational, visual, and dashboard interfaces over the same model.

## Workflow Loop

A mature workflow should look like this:

1. Human states intent, constraints, or desired change.
2. Agent proposes model changes.
3. Model validation checks schema, constraints, traceability, and acceptance readiness.
4. Human reviews high-leverage decisions.
5. Agent generates or updates implementation, tests, docs, and task stream.
6. Agent runs behavioral, visual, boundary, and dependency checks.
7. Evidence is attached to the model.
8. Controller marks accepted changes live when ready.
9. Projections regenerate from the model.

## Minimum First Slice

The first useful slice should prove the loop without over-modeling:

1. Freeze and formally validate the native-first software modeling fixture.
2. Human-review JSON storage, query, and controller as representative state, declarative behavior,
   and orchestration patterns.
3. Migrate and independently package all ten Bibliotek component contracts at that level.
4. Model the Vellis composition, actor-visible use cases, 27 façade actions, and Python/MCP
   realizations.
5. Generate useful component/application pages and implementation handoffs from the model.
6. Retire the frozen Markdown baseline only after formal validation and human approval.

## Success Criteria

The model is worth maintaining only if it accelerates engineering work.

Early success criteria:

- Agents can answer impact questions from the model without re-reading every document.
- Generated specs remain equivalent to current hand-authored specs.
- Acceptance readiness can be checked from model data.
- Component boundary violations are easier to catch.
- Implementation handoffs are generated from accepted model slices.
- Test evidence links directly to invariants and contracts.
- Human review focuses more on design judgment and less on artifact synchronization.

## Design Constraints

The model and methodology should preserve Vellis's design values:

- modularity
- reusability
- narrow scope
- invariant ownership
- low coupling
- simplicity
- elegance
- verifiability

Do not build a giant ontology for its own sake. Start with the model elements needed to make engineering work easier to understand, maintain, test, and extend.

## Open Questions

- Which headless conformant validator best satisfies pinned imports, source diagnostics, CI
  portability, and redistribution requirements?
- What model clarifications emerge from implementation and black-box verification of the three
  representative patterns?
- Which additional documentation projections would make model review easier after cutover?
- When does a second application justify extracting a reusable configurable MCP/REST adapter?
- What evidence should be required before a model element can be accepted?
- How should model changes, implementation changes, and task-stream changes be migrated and cut over together?
- What user interface best supports human review of model changes without requiring humans to inspect raw graph data?
