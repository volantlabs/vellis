# Canonical Component Modeling Pattern

Use one library package per reusable component and preserve its stable `component.*` identity.

## Required model content

1. Imports of the foundation and owning shared-value packages.
2. Boundary-crossing `attribute def` values and identity-bearing `item def` records.
3. `action def` public and construction contracts with exact inputs, outputs, defaults,
   multiplicity, principal failures, and action-scoped semantics.
4. A `part def` for the active component with `@SpecIdentity`.
5. Abstract state features annotated with `@StateAuthority`.
6. Repeated performed actions for provided contracts; `perform action` is the provided-role
   semantics and needs no duplicate provided-role annotation.
7. Referential action features annotated as required capabilities with explicit provider
   cardinality.
8. State-access dependencies from every performed action to canonical/derived/external state or an
   explicit no-state-effect declaration.
9. Requirements or complete constraints for preconditions, effects, failure effects, and invariants.
10. Verification cases covering coherent boundary obligations.

## State and effects

- Model conceptual state, not dictionaries, tables, helper objects, or storage-engine layout.
- Separate canonical state from derived indexes, caches, snapshots, and external resources.
- Use `@StateAccess` on a standard dependency to declare read, create, write, or delete access.
- A read-only action still receives an explicit no-state-effect obligation.
- Express a complete before/after relation as a constraint when practical; otherwise use a concise
  normative action-scoped requirement.
- Do not use state-access metadata on action-to-action dependencies. Use a capability-use
  dependency for delegation and reserve state access for actual abstract state features.
- An enum-valued status plus transition requirements is often the right model for a request-driven
  record lifecycle. Use an exhibited state only when state activation, event-triggered transitions,
  or state-enabled behavior is actually part of the modeled semantics.

## Required capabilities

Use referential action usages for singular operations. Define a coherent read-view part only when a
consumer truly requires several operations over one stable view. Satisfy capabilities with directed
dependencies annotated as contract satisfaction, never value bindings. Do not repeat the provider
role or composition role as strings when `perform action` and the dependency endpoints already say it.

## Logical contract and realization

Keep implementation bindings in realization packages on concrete specializations or usages, not on
the reusable logical component definition. A logical component may have several conforming language,
runtime, deployment, or transport realizations; none is part of its black-box meaning unless that
choice is itself an observable contract.

## Public types and failures

Model values and concrete failures that cross the component boundary. Do not model Python base
exception families merely because they organize implementation inheritance.

Make external encodings recoverable from the model. Declare a namespace naming profile when public
member names or enum literals follow a systematic encoding, and annotate exceptions with an exact
external name. Do not assume a Rust, Python, JSON, protobuf, or transport generator will infer
abbreviations or legacy spellings such as `lt`, `data_object`, or `properties_only` correctly.

Preserve public field names, multiplicity, defaults, and concrete failure distinctions when
revising an accepted contract. Do not replace a typed public value with `JsonObject` unless JSON itself is the accepted
semantic type. When callers may omit identity on create but stored results always have identity,
model distinct request/stored forms or an explicit postcondition.

## Verification

A verification case may cover a coherent group of actions and invariants. Evidence identifies the
boundary suite or artifact; model-level traceability need not mirror individual test functions.
Every accepted obligation must nevertheless be reachable from a verification objective; grouping
does not mean leaving obligations unreferenced.
