# Canonical Component Modeling Pattern

Use one library package per reusable component. Let standard SysML relationships carry the design;
add metadata only for governance or traceability that SysML does not already express.

## Component shape

1. Give the component `part def` a stable SysML short name such as
   `part def <'component.domain.name'> Name`.
2. Model immutable records, requests, results, options, and failure data with `attribute def`.
   Use `item def` when occurrence identity or lifecycle matters to the contract.
3. Define each public invocation with an `action def` and exact typed inputs, outputs, defaults,
   multiplicities, failures, and observable meaning.
4. Expose provided operations with explicitly multiplicited `perform action` features.
5. Model conceptual component state as features of the component definition:
   ordinary composite features for component-owned state, `derived` features for projections, and
   `ref` features for independently existing resources or collaborators.
6. Relate performed actions to the state or collaborators they use with ordinary dependencies and
   concise semantic documentation. Give reads and rejected mutations explicit no-effect guarantees.
7. State complete predicates as constraints. State other testable obligations as requirements with
   the relevant action or component as subject.
8. Group coherent obligations in verification cases and identify concrete evidence separately.

## Collaborators and composition

Choose the required-capability shape by lifetime:

- An invocation-scoped collaborator or read view is a typed action input. The caller supplies one
  for that occurrence; the component does not retain it.
- A collaborator retained by a component occurrence is a multiplicited `ref part` role on the
  component definition.
- An application declares actual part usages and binds a retained referential role to the same part
  occurrence, for example `bind coordinator.store = store;`.

Binding asserts identity/equality. It is appropriate when the referential role and application part
are the same occurrence. Never bind two performed action usages merely to mean “call this provider”;
an invocation relationship is not equality of every action occurrence.

Use a coherent read-view part definition when several operations must observe one logical view.
Otherwise prefer the smallest public collaborator contract that communicates the need.

## State and behavior

- Model canonical domain state, not dictionaries, tables, helper objects, or storage layouts.
- Distinguish owned state, derived features, snapshots, configuration, and independently durable
  resources using native feature kinds and documentation.
- Use `calc def` only for a reusable computation with an actual result expression. Use
  `constraint def` only for a complete Boolean predicate. Never create a hollow calculation,
  constraint, state, port, or interface as a decorated prose container.
- Use an enum-valued status plus transition requirements for a record lifecycle unless activation,
  event-triggered transitions, or state-enabled behavior is intentionally modeled.
- Decompose actions and add successions only when their ordering is part of the black-box contract.

## Identity, encoding, and metadata

- Use SysML short names for stable qualified identities and for external enum spellings that differ
  from the element name, such as `enum <'properties_only'> propertiesOnly;`.
- Keep logical names and encodings language-neutral. Model exact serialized names only when they are
  public interchange semantics.
- Do not recreate native identity, provided/required role, dependency, state ownership, or endpoint
  semantics in a project annotation.
- Keep lifecycle approval, realization links, evidence links, and other project governance metadata
  small and visibly separate from the logical contract.

## Realization and views

Put allocations and implementation bindings in realization packages, not reusable logical
component definitions. Define viewpoints for recurring stakeholder concerns and views that expose
and filter the relevant model elements. Generated prose and diagrams are projections of these
elements, never parallel specifications.
