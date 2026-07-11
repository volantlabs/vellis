# Contributing

Vellis is an early-stage component library. Contributions should preserve the repository's component-first design style: small boundaries, explicit invariant ownership, and black-box tests.

## Local Setup

Install `uv` and `just` first — see the Development Setup section of `README.md` for install commands and prerequisites (Python 3.14 is provisioned automatically by `uv`).

```sh
just setup
just check
```

Use `uv` for Python commands and `just` for project tasks.

## Submitting Changes

Fork the repository, create a topic branch, make your change, run `just check`, and open a pull request against `main`. Keep pull requests focused on a single concern and describe any component-spec updates in the PR description.

## Before Opening A Change

- Read `AGENTS.md` for repository rules.
- Update component specs when public behavior, owned state, dependencies, invariants, or verification expectations change.
- Prefer focused changes over broad refactors.
- Add or update boundary tests for component behavior.
- Run `just check` before submitting.

## Component Changes

Textual SysML under `model/bibliotek/` and `model/vellis/` is the authored design for new
component and application work. Generated reference pages under `docs/reference/` are review aids,
not alternate contracts. The former Markdown specs under
`docs/migration/component-spec-baseline/` are frozen migration evidence and must not be edited as
the current design.

Accepted model contracts are human-owned. If a change requires altering an accepted public
contract, surface the change and get maintainer approval before changing the model and its
realizations together.
