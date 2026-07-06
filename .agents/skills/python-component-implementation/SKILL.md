---
name: python-component-implementation
description: Implement, review, or revise Vellis component code in Python from component specs. Use when creating Python component directories, protocols, component classes, reference implementations, or boundary tests for docs/components specs.
---

# Python Component Implementation

Use this skill after reading the relevant component spec. Preserve the spec's provided contracts, required contracts, owned state, invariants, non-responsibilities, and change rules.

This skill is the Python realization of language-neutral component specs. The spec under `docs/components/` is the source of truth; this skill governs only how that contract is expressed in Python. Keep Python-specific choices — protocols, dataclasses, test frameworks, packaging — inside the implementation, and do not push them back into the spec.

## Workflow

1. Read the component spec under `docs/components/`.
2. Confirm the implementation root from `code.roots`.
3. Create or update one Python directory for the component.
4. Put public boundary definitions in `protocol.py`.
5. Put concrete component class code in `implementation.py` or tightly scoped implementation modules.
6. Put a runnable reference composition in `reference.py`.
7. Put boundary tests under the component's `tests/` directory.
8. Run the narrowest relevant tests and report verification evidence.

## Directory Shape

Use this default structure:

```text
components/<domain>/<name>/
  __init__.py
  protocol.py
  implementation.py
  reference.py
  tests/
    test_<domain>_<name>_contract.py
```

Map component IDs to implementation directories by removing the `component.` prefix and replacing dots with path separators. For example, `component.storage.json_file` maps to `components/storage/json_file/`.

Add private helper modules only when they clarify implementation. Keep helpers inside the component root.

## Protocol File

`protocol.py` defines the consumer-facing Python boundary:

- `typing.Protocol` interfaces for component classes.
- Public dataclasses or typed structures used by the protocol.
- Public exception types or error result types.
- Type aliases that are part of the component contract.

Do not put private helper structure, filesystem details, adapter wiring, or test-only behavior in `protocol.py`.

## Implementation

Implement components as Python classes. The class should encapsulate:

- owned state
- path, input, and dependency validation
- invariant enforcement
- public operations named by the component contract
- error mapping promised by the component spec

Keep component-owned state and invariant logic inside the component root. Do not move state ownership into reference applications, global modules, or shared utilities unless the component spec is updated and the human owner approves.

Use standard-library features first unless the spec or existing project conventions justify an external dependency.

## Reference Implementation

`reference.py` should be runnable on its own and useful as a test target. It may expose a small factory such as `create_reference_component()`.

Use in-memory dependencies by default for required contracts and related abstractions. If the component's own public contract requires durable local state, such as filesystem-backed storage, use temporary local state rather than weakening the contract.

The reference composition should demonstrate the component boundary. It should not become the source of truth for behavior; the component spec remains normative.

## Tests

Prefer tests that exercise the public protocol and boundary behavior:

- contract tests for each provided operation
- invariant tests
- dependency or forbidden-import checks when relevant
- side-effect tests for owned state and non-responsibilities
- reference tests that can run against `reference.py`

Avoid tests that only lock down private helper behavior unless those helpers are the only practical way to prove a boundary property.

## Spec Sync

If implementation work reveals unclear or mismatched public behavior, update the component spec or record an open question before encoding the behavior only in code.

Do not change accepted contracts, owned state, dependencies, invariants, runtime assumptions, or lifecycle status without explicit human approval.
