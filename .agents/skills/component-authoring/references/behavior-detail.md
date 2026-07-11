# Choosing Behavioral Detail

## Mandatory

For every public action, make these contract-significant facts recoverable from the model:

- legal inputs, defaults, outputs, and principal failures;
- required capability reads;
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

For an existing accepted component, also ask whether an implementer using only the revised model
would preserve the same legal calls, defaults, results, failures, state effects, and deterministic
behavior. If not, the revision is incomplete or is a contract change even if its high-level
description sounds correct.
