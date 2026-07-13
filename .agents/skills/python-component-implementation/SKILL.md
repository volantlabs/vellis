---
name: python-component-implementation
description: Implement, review, or revise Python realizations of components from accepted textual SysML v2 contracts and generated views. Use when creating or aligning Python protocols, component classes, reference implementations, implementation bindings, or black-box contract tests.
---

# Python Component Implementation

Use the accepted SysML/KPAR model and its generated component view as the contract. Python is one
realization of that language-neutral design.

Judge the realization at modeled boundaries. Matching private structure, algorithms, helper
decomposition, or another implementation's incidental behavior is neither required nor preferred.
The same accepted model may be realized in another language when it preserves the modeled
structure, behavior, state effects, failures, invariants, composition contracts, and verification
obligations.

## Workflow

1. Locate the component by stable ID in the repository's canonical model package.
2. Resolve the accepted library package version and read its public values, actions, retained
   collaborator roles, state, required constraints, asserted satisfiers, failures, and verification
   cases. Treat top-level documentation as explanation, not as an unmodeled obligation.
3. Locate the matching concrete realization and confirm its code root and symbol from
   `@ImplementationBinding`; do not expect language bindings on the reusable logical component.
4. Implement or revise the consumer-facing Python protocol.
5. Encapsulate canonical state and invariant enforcement inside the component root.
6. Supply action-scoped collaborators and wire retained referential roles only through modeled
   public boundaries; do not reach through another component's internals.
7. Consume structured implementation-neutral conformance objectives when available; add or update
   black-box tests derived from their subject-compatible verification cases and evidence groups.
8. When implementation work forces an observable choice the model does not settle, stop treating
   it as a private coding decision: propose the language-neutral contract clarification or record
   realization drift. Incidental helper, library, and representation choices remain private.
9. Run the narrowest component tests, `just model-check`, and relevant repository checks.

## Realization Rules

- Preserve model action signatures, defaults, results, principal failures, state effects, and invariants.
- Python exception base classes and inheritance are realization structure unless independently modeled.
- Private helpers, data structures, algorithms, indexes, and performance choices remain implementation-owned.
- Derived indexes must remain consistent with modeled canonical state but need not be modeled as code structure.
- Constructor injection, service lookup, messaging, or another runtime mechanism may realize the
  same modeled collaborator roles; the mechanism does not redefine the logical contract.
- Keep application composition and runtime adapters outside the reusable component implementation
  unless the accepted model assigns that behavior to the component.
- Do not change accepted contracts, ownership, dependencies, lifecycle, or invariants for implementation convenience.

## Drift Handling

If code or tests disagree with the model:

1. Use `model-hygiene-review` when the disagreement may reflect migration loss, a predecessor
   contract, an intentional codec, or a later implementation decision.
2. Preserve the accepted model unless evidence establishes a correction to already approved meaning
   or the human owner approves a contract change.
3. Report the model element, implementation symbol, difference, expected behavior, and verification
   needed using the repository's drift or decision workflow.
4. Do not expand the model to mirror incidental Python behavior.

## Python Shape

Use the repository's existing component root and conventions. When none exist, a suitable default is:

```text
components/<domain>/<name>/
  protocol.py
  implementation.py
  reference.py
  tests/
```

`protocol.py` contains only boundary-crossing protocols, values, and concrete public failures.
Implementation modules own state and behavior. Reference compositions demonstrate the boundary but
never become the semantic source of truth.

## Verification

Prefer protocol-level contract tests, invariant/property checks, failure no-effect checks,
dependency checks, and reference-composition tests. A coherent test suite may cover several model
requirements; do not require one Python test function per invariant.
