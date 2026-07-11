---
name: component-authoring
description: Design, create, review, revise, extract, split, merge, or validate reusable software components and application compositions as textual SysML v2 black-box models. Use when Codex needs to define public actions and values, required capabilities, abstract owned state, action effects, invariants, lifecycle, verification objectives, component boundaries, or model-to-implementation drift.
---

# Component Authoring

Author the durable component and application design in textual SysML v2 under `model/`. Treat
generated Markdown as a view, never as an independent contract.

## Goal

Model enough contract-significant structure and behavior that a human or agent can:

- understand what the component owns and exposes;
- invoke and compose its public contracts;
- reason about abstract state changes and invariant preservation;
- substitute another conforming realization;
- derive black-box verification scenarios.

Leave private helpers, algorithms, implementation data structures, performance strategy, and
language-specific type hierarchies to realizations.

## Conformance Hierarchy

Treat every chosen abstraction boundary as an engineered black box. A component realization
conforms when its public structure, behavior, abstract state effects, failures, invariants, and
verification obligations match the model, regardless of implementation language or internal
design. A composed subsystem or application is another modeled black box: its internal roles must
conform to their component contracts, and its own external actions, behavior, state, invariants,
and use cases must conform at the higher boundary.

Model downward into algorithms, deployment, hardware, or implementation structure only when that
layer is itself an intentional engineering subject or affects an observable contract. Do not make
implementation fidelity the default completeness criterion.

## Required Resources

- Read `references/component-modeling-pattern.md` before authoring or materially revising a model.
- Read `references/behavior-detail.md` when deciding how much behavior to formalize.
- Read `references/model-organization.md` when creating or changing a model library, package
  boundary, shared vocabulary, application/library dependency, or runtime realization.
- Read `references/application-composition.md` for application, controller, adapter, or use-case work.
- Read `references/boundary-quality.md` when reviewing ownership or considering a split or merge.
- Read `references/examples.md` when a representative storage, query, or controller pattern helps.

## Workflow

1. Locate or create the owning model package, confirm its library/application/realization layer,
   and inspect any current generated view.
2. When revising an existing accepted component, preserve its observable public boundary unless a
   human explicitly approves a contract change.
3. Inspect current implementations and tests as realization evidence, not automatic contract truth.
4. Establish the smallest coherent boundary around one responsibility and its invariants.
5. Define boundary-crossing values or identity-bearing items without changing their public shape.
   Separate request and stored forms when identity is optional only on creation.
6. Define every public and construction action with exact typed inputs, outputs, defaults,
   multiplicity, principal failures, and observable result semantics.
7. Define required capabilities independently of current wiring and declare provider cardinality.
8. Model abstract canonical, derived, and externally referenced state.
9. Relate every action to the state or capability it reads, creates, writes, or deletes; state
   explicit no-effect behavior for reads, previews, validation, and rejected mutations.
10. Add concise preconditions, effects, failure effects, ordering, and invariant obligations.
11. Model lifecycle only when it changes permitted operations or observable results. Use an
    enum-valued status and transition obligations for request-driven record lifecycles; use an
    exhibited state only when activation/event semantics are intentionally modeled.
12. Add verification cases that explicitly cover every accepted obligation, directly or through a
   named coherent verification group.
13. Run the repository's model checks and regenerate human views, then review the complete boundary
    rather than only filenames or operation names.
14. Ask whether a conforming implementation in a different suitable language could be built from
    the model and pass black-box conformance at this boundary. Repair the model if correct callers,
    state effects, results, failures, or composition behavior would still require guessing.

## Fidelity Rule

Use three levels:

1. Structural contract for every component: types, actions, failures, capabilities, cardinality, roles.
2. State semantics for every stateful component: state authority, access, effects, failure atomicity,
   invariant preservation.
3. Detailed behavior only where consumers must predict it: declarative matching, transition tables,
   observable ordering, or rollback orchestration.

Model a rule only when it affects legal invocation, output meaning, abstract state, failure effects,
invariant preservation, substitutability, or composition.

Compression is allowed only after those facts are preserved. Fewer lines are not evidence of a
better model. A compact requirement may replace several prose bullets only when it has the same
observable meaning and does not permit additional incompatible implementations.

## Contract Preservation

When revising or re-expressing an accepted component, every contract-significant fact needs one
disposition:

- represented structurally in SysML;
- represented by a typed value, enum, state, calculation, constraint, or requirement;
- intentionally excluded as rationale, private implementation, or non-normative agent guidance;
- recorded as an explicit contract change requiring human approval.

Do not silently rename fields, collapse error families, change optionality/defaults, replace a
typed contract with generic JSON, change state ownership, add ordering promises, or substitute a
different dependency shape. Construction actions such as `open`, `empty`, and `import_snapshot`
are public contracts and must appear in both the model and generated views.

## Hard Stop Rule

Stop adding detail when contract-significant behavior is sufficient for composition, substitution,
design reasoning, and black-box verification. Do not pursue direct code generation or eliminate
intentional implementation freedom.

This stop rule applies only after contract preservation is established. It cannot justify omitting
accepted inputs, outputs, fields, defaults, failures, state categories, invariants, or observable
behavior.

## Governance

- Humans approve accepted boundaries, public contracts, state ownership, dependencies, and invariants.
- Fidelity repairs may translate already-approved meaning without changing it.
- If model, implementation, and tests disagree, record a compact drift entry; do not silently choose code.
- Keep runtime and language choices outside the logical component unless they are observable contract terms.
- Put genuinely shared public semantics in an owning library package; do not use an application,
  realization, or global grab bag as the accidental owner of reusable types.
- Use bindings only for value equality. Use dependencies for capability satisfaction and state access.
- Let native constructs carry their native meaning: performed actions are provided capabilities,
  interfaces connect ports, exhibited states are activated behavior, and allocations map logical
  elements to realizations. Add metadata only for semantics the language construct does not express.

## Outputs

For authoring or revision, produce:

1. Updated SysML source.
2. Updated generated human view.
3. A concise list of contract decisions or implementation drift, if any.
4. Verification results.

For review, report material boundary, contract, state, invariant, composition, and verification gaps.
Keep implementation inspection focused on evidence needed to assess the public design.
