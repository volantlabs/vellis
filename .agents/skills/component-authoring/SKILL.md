---
name: component-authoring
description: Design, create, review, revise, split, merge, or validate reusable software components and application compositions as textual SysML v2 black-box models. Use when Codex needs to define public actions and values, collaborator roles, abstract owned state, action effects, invariants, lifecycle, verification objectives, component boundaries, or system composition.
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

- Use the `sysml-reference` skill before making or reviewing a SysML/KerML syntax or semantics
  decision. Cite the relevant specification section and page for consequential choices.
- Read `references/component-modeling-pattern.md` before authoring or materially revising a model.
- Read `references/behavior-detail.md` when deciding how much behavior to formalize.
- Read `references/model-organization.md` when creating or changing a model library, package
  boundary, shared vocabulary, application/library dependency, or runtime realization.
- Read `references/application-composition.md` for application, controller, adapter, or use-case work.
- Read `references/boundary-quality.md` when reviewing ownership or considering a split or merge.
- Read `references/examples.md` when a representative storage, query, or controller pattern helps.

## Workflow

Before following the component workflow, search the pinned SysML/KerML reference corpus for every
language construct whose syntax or semantics affects the design. Record the specification, section,
and page basis, and distinguish it from repository modeling conventions.

1. Locate or create the owning model package and confirm its library, application, view, or
   realization layer.
2. Establish the smallest coherent boundary around one responsibility and its invariants.
3. Give public elements stable SysML short names for durable model identity. Model an external
   encoding as the logical name itself or as an explicit realization codec.
4. Define boundary-crossing values and identity-bearing items. Separate request and stored forms
   when identity is optional only on creation.
5. Define every public and construction action with exact typed inputs, outputs, defaults,
   multiplicity, principal failures, and observable result semantics.
6. Model invocation-scoped collaborators as typed action inputs and retained collaborators as
   multiplicited referential part roles.
7. Model abstract canonical, derived, and externally referenced state with native feature kinds.
8. Relate every action to the state or collaborator it reads, creates, writes, or deletes; state
   explicit no-effect behavior for reads, previews, validation, and rejected mutations.
9. Put every normative obligation in a requirement `require constraint`; use textual constraints
   when a complete Boolean expression would obscure or weaken the intended rule.
10. Assert which component or action usage satisfies each accepted requirement. Keep satisfaction
   separate from evidence that verifies the assertion.
11. Model lifecycle only when it changes permitted operations or observable results. Use an
    enum-valued status and transition obligations for request-driven record lifecycles; use an
    exhibited state only when activation/event semantics are intentionally modeled.
12. Add verification cases whose subjects are compatible with the requirements they verify. Use
   separate action, component, and composition cases when their subjects differ.
13. For applications, bind retained collaborator roles to actual part occurrences and model
    actor-visible use cases and application-owned invariants.
14. Use a `view def` for a reusable projection. Introduce a viewpoint only when stakeholders and
    concerns are explicitly modeled.
15. Run a conformant SysML parser/linker/semantic validator as well as repository profile checks,
    validate downstream products against their packaged dependencies, then regenerate
    parser-backed projections and review the complete boundary. Grammar matching and regular
    expressions alone do not establish language conformance.
16. Ask whether a conforming implementation in a different suitable language could be built from
    the model and pass black-box conformance at this boundary. Repair the model if correct callers,
    state effects, results, failures, or composition behavior would still require guessing.
17. Before retiring a predecessor specification, disposition every durable fact: put contractual
    structure and behavior in the model, retain rationale/tutorial/operations/open questions in a
    clearly non-normative document, record implementation disagreement as realization drift, and
    identify any superseded statement by the model decision that replaced it. File deletion alone
    is never evidence that migration is complete.

## Fidelity Rule

Use three levels:

1. Structural contract for every component: types, actions, failures, collaborators, multiplicities, roles.
2. State semantics for every stateful component: state ownership, access, effects, failure atomicity,
   invariant preservation.
3. Detailed behavior only where consumers must predict it: declarative matching, transition tables,
   observable ordering, or rollback orchestration.

Model a rule only when it affects legal invocation, output meaning, abstract state, failure effects,
invariant preservation, substitutability, or composition.

Compression is allowed only after those facts are preserved. Fewer lines are not evidence of a
better model. A compact requirement may replace several prose bullets only when it has the same
observable meaning and does not permit additional incompatible implementations.

## Contract Evolution

Treat an accepted model as the design authority. Change public names, types, multiplicities,
defaults, failures, state ownership, ordering promises, invariants, or collaborator topology only
as an intentional reviewed contract change. Construction actions are public contracts when callers
depend on them. Implementation evidence may reveal a design question; it does not silently redefine
the model.

When the task is specifically to audit model/realization drift, use `model-hygiene-review` before
authoring changes. Inspect predecessor contracts and chronology: an accepted model can contain a
migration omission or incorrect language transcription, while implementation behavior can be
intentional, incidental, or stale. Classify the authority question before revising either side.

## Hard Stop Rule

Stop adding detail when contract-significant behavior is sufficient for composition, substitution,
design reasoning, and black-box verification. Do not pursue direct code generation or eliminate
intentional implementation freedom.

The stop rule cannot justify omitting inputs, outputs, fields, defaults, failures, state categories,
invariants, or observable behavior that the design intentionally promises.

## Governance

- Humans approve accepted boundaries, public contracts, state ownership, dependencies, and invariants.
- If model, implementation, and tests disagree, surface the design decision; do not silently choose code.
- Keep runtime and language choices outside the logical component unless they are observable contract terms.
- Put genuinely shared public semantics in an owning library package; do not use an application,
  realization, or global grab bag as the accidental owner of reusable types.
- Use binding only for actual equality or identity, including binding a retained referential role to
  the application part occurrence it denotes. Never bind action occurrences as a call relationship.
- Use action inputs for invocation-scoped collaborators and typed dependencies for state access or
  allowed dependency topology. Model an invocation as a nested action performed by the provider,
  with bindings or flows for contract-significant inputs and outputs.
- Let native constructs carry their native meaning: performed actions are provided capabilities,
  interfaces connect ports, exhibited states are activated behavior, and allocations map logical
  elements to realizations. Add metadata only for semantics the language construct does not express.
- Use `default =` for an overridable default value and `=` only for an actual binding. Navigate
  nested features with dot notation and reserve `::` for qualification/redefinition references.
  Quote a required public name when it is a reserved word; do not silently rename the contract.

## Outputs

For authoring or revision, produce:

1. Updated SysML source.
2. Updated generated human view.
3. A concise list of contract decisions or conformance questions, if any.
4. Structured implementation-neutral conformance objectives derived from verification cases.
5. Verification results.

For review, report material boundary, contract, state, invariant, composition, and verification gaps.
Keep implementation inspection focused on evidence needed to assess the public design.

When predecessor material is being retired, also report the non-normative destination of useful
context and the explicit disposition of unresolved model/implementation differences.
