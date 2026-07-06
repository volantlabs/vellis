# Component Spec Template

Use this template for component specs unless the repository already has a stricter convention.

Place specs under:

```text
docs/components/<component-id>.md
```

Use stable lowercase dotted IDs:

```text
component.<domain>.<name>
```

Examples:

```text
component.billing.invoice_preview
component.auth.session
component.notifications.delivery
component.search.indexer
```

## Template

```md
---
id: component.<domain>.<name>
type: Component
status: draft
owner: <team-or-person-or-unknown>
code:
  roots:
    - <path-or-package>
---

# <Component Name>

## Purpose

<One or two sentences describing why this component exists in system/product terms.>

## Responsibilities

- <Behavior, authority, or outcome this component owns.>

## Non-responsibilities

- <Adjacent behavior, authority, or state this component explicitly does not own.>

## Provided contracts

### `<contract name>`

Kind:

- <function | class | protocol | API endpoint | event | message handler | CLI command | job | module | database view | other>

Inputs:

- `<input>`

Outputs:

- `<output>`

Errors:

- `<error>`

Semantics:

- <Externally meaningful behavior of this contract.>
- <Side effects, idempotency, ordering, delivery, consistency, security, or failure behavior if relevant.>

## Required contracts

May consume:

- `<component or external contract>`

Must not consume:

- `<forbidden component or external contract>`

## Owned state

- `<database table, durable record, queue, cache, file, external resource, lifecycle authority, state machine, or identifier this component owns>`

If none:

- None. This component derives its behavior from other components and does not own durable state.

## Invariants

### `<short invariant name or stable invariant id>`

<Property that must remain true across valid implementations. Use a stable ID such as `invariant.<domain>.<component>.<property>` when useful, but do not let formal naming get in the way of a clear invariant.>

## Verification

Required checks:

- `<contract/behavior check, architecture check, dependency check, side-effect check, migration check, or schema check>`

Required evidence:

- `<contract test, golden fixture, property check, trace/log assertion, schema validation, no-write proof, integration evidence, or other boundary-level evidence>`

## Change rules

Agents may:

- <Allowed implementation changes inside the component boundary.>

Agents may not:

- <Changes requiring explicit human approval.>

## Open questions

- <Unresolved boundary, contract, dependency, state, invariant, verification, lifecycle, or relation question.>
```

## Status Values

- `draft`: Proposed boundary; useful for discussion and early implementation but not authoritative.
- `accepted`: Human-approved boundary; agents must preserve contracts, dependencies, state ownership, invariants, and change rules.
- `deprecated`: Still valid for existing consumers but should not gain new consumers.
- `retired`: Historical only; no active implementation should depend on it.

## Optional Relations

Add this section only when known relationships help humans or agents reason about the component:

```md
## Related components

- <Known parent, peer, replacement, superseded, or deprecated-by component relationship.>
```

Do not add `Related components` just to say that no relationships are known. Do not invent hierarchy, dependency, ontology, or graph structure for future modeling. If a repository later adopts a graph, SysML, or ontology-backed representation, these known relationships can be migrated into that model.

## Optional Runtime Notes

Add this section only when runtime or wiring assumptions are part of the public contract:

```md
## Runtime notes

- <Dependency-injection, broker, queue, transport, process, deployment, delivery, ordering, retry, idempotency, or consistency assumption that is externally meaningful.>
```

Do not add runtime notes for ordinary implementation choices. A component boundary is not automatically a process, service, package, queue, or deployment boundary.

## Design Fit Check

Before finalizing a spec, check that:

- The component scope is no broader than its invariant ownership requires.
- Public contracts have one clear representation for each operation and result.
- Required dependencies are low-coupling public contracts, not private internals or framework choices.
- The component is reusable outside a single app, transport, runtime, or storage representation.
- The boundary can be verified with black-box tests, side-effect checks, and dependency checks.
- Any added abstraction, lifecycle state, adapter, or extension seam has a current consumer, invariant, or verification need.
- The spec stays language- and runtime-neutral: contracts, types, errors, and verification are expressed as externally observable behavior, not as constructs, test frameworks, or tool commands of one implementation.

## Ownership Rule

The owner approves changes to provided contracts, required contracts, owned state, invariants, lifecycle status, and known cross-component relationships. If `owner` is `unknown`, list ownership as an open question before treating the spec as accepted.

## Maintenance Rule

Update the component spec when:

- a public contract changes
- owned state moves
- a cross-component dependency is added, removed, or forbidden
- an invariant is added, weakened, or removed
- verification expectations change
- the component is split, merged, deprecated, retired, or superseded
- implementation reality diverges from the intended component contract
