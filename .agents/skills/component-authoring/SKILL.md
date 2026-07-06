---
name: component-authoring
description: Design, create, review, revise, extract, split, merge, or validate lightweight component specifications for human-designed and agent-implemented systems. Use when Codex needs to reason about component boundaries or define black-box software components, public contracts, required dependencies, owned state, invariants, verification evidence, lifecycle status, known relationships between components, or agent change rules before implementation or after code changes.
---

# Component Authoring

Use this skill to design component boundaries and produce component specs that let humans reason about system structure while agents implement validated slices inside clear boundaries.

A component spec is a durable black-box contract. It is not an implementation plan, task list, scratchpad, or exhaustive source-file inventory. It captures the system meaning of a component: why it exists, what it owns, what it exposes, what it may depend on, what it must never do, and how its behavior can be verified from outside the boundary.

Optimize first for human-readable component specs and agent-safe implementation boundaries. Prefer stable names, explicit ownership, clear dependencies, and known relationships because they preserve the option to project specs into a knowledge graph, SysML, or another MBSE-style model later. Do not add ontology terms, graph structure, or relationships solely for future modeling.

## Resources

- Read `references/component-spec-template.md` when drafting or rewriting a component spec.
- Read `references/boundary-quality.md` when reviewing a boundary, deciding whether to split or merge components, or resolving ambiguous ownership.
- Read `references/minimal-example.md` when an example would clarify expected detail level.

## Core Principle

Define the smallest coherent system responsibility that can hide implementation details behind explicit contracts.

Favor reusable, self-contained behavior with narrow scope, low coupling, and explicit invariant ownership. A component spec should define what behavior is provided and what contracts are required without assuming whether the implementation is wired in-process, dependency-injected, message-driven, or deployed as a distributed runtime service. Include runtime topology, transport, queue, broker, or dependency-injection details only when they are externally meaningful parts of the component contract.

A component spec is also language-neutral: it describes externally observable behavior and contracts, not the constructs, test frameworks, or tool commands of any one implementation language. Express verification as boundary behavior and evidence; concrete commands and language mechanics belong to the implementation layer.

Prefer elegant designs: one clear representation for each operation, one owner for each invariant, one public contract shape that current consumers can understand and test. Do not add abstractions, lifecycle states, adapters, or extension seams only to preserve theoretical future flexibility.

The spec should let a human say:

- I know what this component means.
- I know what it owns.
- I know what it exposes.
- I know what it may depend on.
- I know what it must never do.
- I know how to verify delivered behavior.
- I do not need to know how every helper inside it is factored.

## Human And Agent Swim Lanes

Keep humans focused on leverage points:

- choosing system boundaries
- naming durable concepts
- approving ownership
- defining public contracts
- controlling cross-component dependencies
- identifying invariants and non-responsibilities
- deciding verification evidence
- accepting validated slices

Give agents freedom inside the component boundary:

- implement private internals
- add local helper modules
- refactor internal structure
- add tests and validation around public contracts
- improve implementation quality without changing ownership, dependencies, contracts, invariants, or externally observable behavior

Require explicit human approval before changing accepted component contracts, owned state, lifecycle status, cross-component dependencies, or invariants. Treat `accepted` as a repository governance status defined by the active project instructions; if the repository has not defined who may accept specs, list acceptance authority as an open question.

## Acceptance Readiness

Before a human owner marks a component spec `accepted`, check that:

- Public contracts are concrete enough for an independent implementation.
- Required and forbidden dependencies are explicit.
- Owned state and non-responsibilities are clear.
- Invariants are externally meaningful and testable.
- Verification requirements are specific enough to prove boundary behavior.
- The boundary is modular, reusable, low-coupling, and no broader than its invariant ownership requires.
- The public surface is simple enough to implement, test, and explain without speculative extension mechanisms.
- Open questions do not leave current public behavior ambiguous.

## Workflow

1. Identify the candidate component as a system responsibility, not merely a class, package, service, or directory.
2. Name it with a stable dotted ID such as `component.billing.invoice_preview`.
3. Define purpose in product/system language.
4. Define responsibilities and non-responsibilities in bounded active language.
5. Define provided contracts with behavior, not only type signatures or transport details.
6. Define required contracts, separating allowed dependencies from forbidden dependencies and avoiding concrete wiring assumptions unless required by the public contract.
7. Define owned state, or explicitly state that the component is stateless/read-only.
8. Define externally meaningful invariants.
9. Define verification checks and evidence that prove behavior at the component boundary.
10. Define agent change rules that preserve the human-owned design boundary.
11. Put uncertainty under `Open questions`; do not hide unresolved ownership or boundary decisions in confident prose.

## Existing-Code Extraction

When inferring a spec from code:

1. Inspect the likely component root.
2. Identify public entry points.
3. Identify outbound dependencies.
4. Identify state reads and writes.
5. Identify tests that exercise public behavior.
6. Separate observed implementation facts from intended component contract.
7. Draft uncertain ownership, contract, dependency, state, or invariant decisions under `Open questions`.
8. Do not overfit the spec to private helper structure.

Use this distinction whenever code and intended design may differ:

```text
Observed current implementation:
  What the code currently appears to do.

Intended component contract:
  What the component should mean and guarantee.
```

## Output Modes

For a new component, output:

1. The complete component spec.
2. Assumptions.
3. Open questions requiring human judgment.

For an existing-code extraction, output:

1. Candidate component spec.
2. Observed implementation facts.
3. Intended-contract assumptions.
4. Open questions.
5. Risks where code and desired boundary appear misaligned.

For a review, output:

1. Boundary assessment.
2. Missing or weak sections.
3. Suggested edits.
4. Questions requiring human judgment.
5. Optional revised spec.

For an iteration, output:

1. Revised component spec.
2. Concise changelog of spec changes.
3. New or remaining open questions.

For implementation handoff, output:

1. The accepted or draft component spec being implemented.
2. The allowed implementation roots and required verification.
3. Any contract, dependency, state, invariant, or runtime assumptions that need human approval before implementation.
4. A concise implementation boundary summary. Do not produce a detailed task plan unless the user asks for one.

## Authoring Rules

- Keep the spec concise and black-box oriented.
- Prefer concrete contracts and invariants over vague prose.
- Write non-responsibilities as containment rules that prevent drift.
- Keep component scope tied to invariant ownership.
- Prefer low-coupling public contracts over convenience access to adjacent component internals.
- Prefer one canonical representation for each operation and result.
- Do not turn the spec into an implementation plan.
- Do not document every private helper.
- Do not create specs for every class or source file.
- Do not invent ownership unsupported by code or human direction.
- Do not expand a component boundary to make implementation easier.
- Do not make a component responsible for adjacent behavior merely because current code reaches there.
- Do not introduce optional abstraction layers, lifecycle states, or extension seams without a current consumer, invariant, or verification need.
- Update the spec when public contracts, owned state, dependencies, invariants, verification requirements, lifecycle status, or known component relationships change.
