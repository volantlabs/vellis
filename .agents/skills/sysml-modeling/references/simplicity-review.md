# Simplicity Review

Apply this review after the model expresses a coherent outcome and before implementation authorization.

## Justification test

For every element, ask:

1. Which current use case, requirement, invariant, or verification objective needs it?
2. What claim becomes false or unverifiable if it is removed?
3. Is it the simplest native representation of that claim?

Remove or defer the element when these questions have no concrete answer.

## Warning signs

- The model mirrors files, classes, methods, handlers, or call graphs.
- Services, runtimes, adapters, controllers, ledgers, or repositories appear before a behavior requires them.
- Request and response types merely wrap placeholder or generic JSON.
- The same fact is represented in multiple authoritative forms.
- Lifecycle machinery exists without activated behavior or a current decision need.
- Extension points, interchangeable layers, or configuration surfaces have no current consumer.
- A distinction exists only because predecessor code contained it.

## Final pass

Prefer one clear representation and a laminar path from owner intent to use case, requirement, satisfier, verification, and later generated source. Record unresolved choices as questions. Do not model speculative answers.
