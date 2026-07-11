# Choosing Behavioral Detail

## Mandatory

For every public action, make these contract-significant facts recoverable from the model:

- legal inputs, defaults, outputs, and principal failures;
- invocation-scoped collaborator inputs and retained collaborator-role reads;
- abstract state read/write/create/delete effects or explicit no effect;
- success and failure postconditions that preserve component invariants;
- ordering, consistency, or idempotency only when promised to consumers.

## Selective detail

Use calculations, constraints, transition tables, or action successions only when two otherwise
conforming implementations could differ in a way that changes correct use or composition.

Good selective-detail examples:

- JSON-kind-aware query equality and predicate semantics;
- migration lifecycle transitions;
- deterministic result ordering promised by a read contract;
- controller validation-before-apply and rollback boundaries.

Choose the native behavior construct for its actual semantics. A state definition models activated
behavior and event-triggered transitions; it is not a richer spelling of a status enum. An interface
connects ports and may carry defined flows; it is not a generic software API. A succession constrains
occurrence ordering; it is not a call graph.

A calculation defines a reusable computation and must return a result. A constraint is a complete
Boolean predicate. When a rule cannot be expressed completely and correctly with the supported
expression subset, put normative text inside a requirement `require constraint` rather than using
top-level documentation or a hollow formal construct.

Use native action decomposition for contract-significant orchestration. A nested action represents
the invoked occurrence; a provider part performs it; its directed parameters redefine the typed
action parameters and bind or flow contract values;
successions constrain externally meaningful order. A dependency may record allowed topology or
state access, but does not itself mean that an invocation occurs.

## Leave open

Do not model private helper calls, branch structure, loops, temporary values, algorithms,
implementation data structures, serialization mechanics below the public encoding contract, or
performance strategies.

## Completeness test

Stop when a reviewer can answer:

1. What may I invoke and what can result?
2. What state is authoritative?
3. What does each action read or change?
4. What remains true after success or failure?
5. What dependencies must a composition provide?
6. What implementation choices intentionally remain open?

Also ask whether two conforming realizations could differ in black-box behavior the design needs to
settle. If so, formalize that distinction; if the difference is intentionally open, say so once and
stop modeling deeper.
