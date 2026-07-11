# Canonical Component Modeling Pattern

Use one library package per reusable component. Let standard SysML relationships carry the design;
add metadata only for governance or traceability that SysML does not already express.

## Component shape

1. Give the component `part def` a stable SysML short name such as
   `part def <'component.domain.name'> Name`.
2. Model immutable records, requests, results, options, and failure data with `attribute def`.
   Use `item def` when occurrence identity or lifecycle matters to the contract.
3. Define each public invocation with an `action def` and exact typed inputs, outputs, defaults,
   multiplicities, failures, and observable meaning. Spell an overridable default as `default =`;
   plain `=` is a binding and must not be used as shorthand for a default.
4. Expose provided operations with explicitly multiplicited `perform action` features.
5. Model conceptual component state as features of the component definition:
   ordinary composite features for component-owned state, `derived` features for projections, and
   `ref` features for independently existing resources or collaborators.
6. Relate actions to abstract state with typed read, create, write, or delete dependencies. State
   explicit no-effect guarantees for reads, previews, validation, and rejected mutations.
7. Model a collaborator invocation as a nested action occurrence performed by the provider. Use
   parameter redefinitions with bindings for input/output equality, and flows for transfer; do not
   substitute a generic dependency. A typed nested action's owned parameters explicitly redefine
   the corresponding parameters of its action definition. Use dot notation to navigate occurrence
   features and `::` to qualify definition members in a redefinition target.
8. Put every normative rule in a requirement `require constraint`. Use a Boolean constraint when it
   is complete and concise, or a textual required constraint when formalization would obscure intent.
9. Assert satisfiers separately from verification. Give each verification case a subject compatible
   with every requirement in its objective and bind concrete evidence to the case. An evidence
   group must resolve to one or more exact test or evidence nodes; file existence alone is not
   verification closure.

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

- Use SysML short names for stable qualified model identities, not as an implicit serialization map.
- Quote a public identifier when its required spelling is a language keyword. Preserve the logical
  name in generated views and realization codecs instead of renaming the contract to placate a
  parser or a repository text extractor.
- If an enum literal is itself a public interchange value, name the logical literal accordingly.
  Put transport-specific renaming in an explicit codec or realization mapping.
- Do not recreate native identity, provided/required role, dependency, state ownership, or endpoint
  semantics in a project annotation.
- Keep lifecycle approval, realization links, evidence links, and other project governance metadata
  small and visibly separate from the logical contract.

## Realization and views

Put allocations and implementation bindings in realization packages, not reusable logical
component definitions. Use view definitions for reusable projections. Use viewpoints only when
stakeholders and concerns are explicitly modeled. Generated prose and diagrams are projections of
these elements, never parallel specifications.

Run an actual SysML parser, linker, and semantic validator against pinned language libraries.
BNF-derived syntax tooling and repository profile checks are useful supplemental gates, but neither
can establish name resolution, typing, multiplicity, specialization, or semantic conformance.
