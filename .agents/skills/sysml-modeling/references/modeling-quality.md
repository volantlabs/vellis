# Modeling Quality

## State and identity

- Use an owned feature for state whose lifecycle and invariants belong to the subject.
- Use a derived feature when its value is determined from other modeled facts.
- Use a reference feature for an independently existing occurrence that is not owned by the subject.
- Do not let a database, document, event, or serialization format dictate the conceptual state model.

## Behavior and structure

- Model actions for externally meaningful behavior or behavior needed to reason about a requirement.
- Add parts only when owned structure is an intentional subject of design.
- Use ports and interfaces only for modeled connected interactions and transfers.
- Use states only for actual activated or event-driven state behavior.
- Define a calculation only when it has an evaluable result.
- Define a constraint only when it is a complete predicate.
- Prefer native SysML semantics to project annotations or prose-shaped pseudo-language.

## Verification closure

For an implementation-authorizing slice, check that:

- the owner outcome is observable;
- requirements state the obligations precisely;
- satisfiers are asserted separately from requirements;
- verification objectives have compatible subjects and decisive evidence;
- failures and effects needed for black-box judgment are present;
- implementation, runtime, persistence, and deployment freedom remains where the product does not constrain it.

Use `$sysml-reference` to ground ownership, reference, derivation, behavior, connection, satisfaction, and verification decisions in the pinned language corpus.
